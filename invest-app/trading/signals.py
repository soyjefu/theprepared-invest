import json
from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import TradeLog, Portfolio, AnalyzedStock
import logging
from decimal import Decimal
from django.db import transaction

logger = logging.getLogger(__name__)

@receiver(post_save, sender=TradeLog)
def on_tradelog_save(sender, instance, created, **kwargs):
    """
    Handles post-save events for TradeLog model.
    Broadcasts the new/updated trade log to the relevant user's channel group.
    """
    logger.info(f"TradeLog signal triggered for Order ID: {instance.order_id}, Status: {instance.status}")

    channel_layer = get_channel_layer()
    group_name = f"trades_{instance.account.id}"

    # Serialize the instance data
    data = {
        "type": "trade_update", # This is the message type for the frontend
        "log": {
            "id": instance.id,
            "symbol": instance.symbol,
            "trade_type": instance.get_trade_type_display(),
            "quantity": instance.quantity,
            "price": float(instance.price),
            "status": instance.get_status_display(),
            "timestamp": instance.timestamp.isoformat(),
            "log_message": instance.log_message,
        }
    }

    # The handler in the consumer is named 'trade_update', so the type here must match.
    # We convert it from snake_case to dot.case for the channel layer.
    message = {
        "type": "trade.update",
        "data": data
    }

    async_to_sync(channel_layer.group_send)(group_name, message)
    logger.info(f"Sent trade update to group {group_name}")

    # Also trigger a portfolio and account balance refresh
    # This is a simple way to notify the client that other data is now stale.
    async_to_sync(channel_layer.group_send)(f"portfolio_{instance.account.id}", {
        "type": "portfolio.update",
        "data": {"type": "portfolio_refresh_required"}
    })

    async_to_sync(channel_layer.group_send)(f"account_{instance.account.id}", {
        "type": "account.update",
        "data": {"type": "account_refresh_required"}
    })
    logger.info(f"Sent refresh requests to portfolio and account groups for account {instance.account.id}")


@receiver(post_save, sender=TradeLog)
def update_portfolio_on_execution(sender, instance, created, **kwargs):
    """
    Listens for executed trades and updates the portfolio accordingly.
    This runs in a transaction to ensure atomicity.
    """
    if instance.status != 'EXECUTED':
        return

    logger.info(f"Portfolio update signal triggered for executed trade: {instance.id}")

    try:
        with transaction.atomic():
            if instance.trade_type == 'BUY':
                # Get the analysis data to set stop-loss/target prices on new entries
                analyzed_stock = AnalyzedStock.objects.filter(symbol=instance.symbol).first()
                stop_loss = analyzed_stock.raw_analysis_data.get('stop_loss_price', instance.price * Decimal('0.9'))
                target_price = analyzed_stock.raw_analysis_data.get('target_price', instance.price * Decimal('1.2'))

                portfolio, created = Portfolio.objects.get_or_create(
                    account=instance.account,
                    symbol=instance.symbol,
                    is_open=True,
                    defaults={
                        'stock_name': analyzed_stock.stock_name if analyzed_stock else instance.symbol,
                        'quantity': instance.quantity,
                        'average_buy_price': instance.price,
                        'stop_loss_price': stop_loss,
                        'target_price': target_price,
                        'entry_log': instance
                    }
                )

                if not created:
                    # It's an existing position, so we update it (add to the position)
                    old_total_value = portfolio.quantity * portfolio.average_buy_price
                    new_total_value = instance.quantity * instance.price
                    total_quantity = portfolio.quantity + instance.quantity

                    portfolio.average_buy_price = (old_total_value + new_total_value) / total_quantity
                    portfolio.quantity = total_quantity
                    # We can also decide if we want to update stop-loss/target prices here
                    portfolio.save()
                    logger.info(f"Updated portfolio position for {instance.symbol}. New quantity: {total_quantity}")
                else:
                    logger.info(f"Created new portfolio position for {instance.symbol}.")

            elif instance.trade_type == 'SELL':
                try:
                    portfolio = Portfolio.objects.get(account=instance.account, symbol=instance.symbol, is_open=True)

                    if portfolio.quantity > instance.quantity:
                        portfolio.quantity -= instance.quantity
                        portfolio.save()
                        logger.info(f"Partially sold {instance.symbol}. Remaining quantity: {portfolio.quantity}")
                    else:
                        portfolio.quantity = 0
                        portfolio.is_open = False
                        portfolio.save()
                        logger.info(f"Fully sold {instance.symbol}. Position closed.")

                except Portfolio.DoesNotExist:
                    logger.error(f"Attempted to sell {instance.symbol}, but no open portfolio position was found for account {instance.account.id}.")

    except Exception as e:
        logger.error(f"Error updating portfolio for trade {instance.id}: {e}", exc_info=True)
