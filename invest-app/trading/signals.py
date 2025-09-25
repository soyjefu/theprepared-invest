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
    Signal handler that broadcasts updates when a TradeLog instance is saved.

    This function is triggered after a TradeLog is saved and sends a message
    via Django Channels to a group specific to the trade's account. This
    allows the frontend to receive real-time updates on trade statuses. It also
    sends refresh requests for portfolio and account data.

    Args:
        sender: The model class that sent the signal (TradeLog).
        instance (TradeLog): The actual instance being saved.
        created (bool): True if a new record was created.
        **kwargs: Wildcard keyword arguments.
    """
    logger.info(f"TradeLog signal triggered for Order ID: {instance.order_id}, Status: {instance.status}")

    channel_layer = get_channel_layer()
    group_name = f"trades_{instance.account.id}"

    data = {
        "type": "trade_update",
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

    message = {
        "type": "trade.update",
        "data": data
    }

    async_to_sync(channel_layer.group_send)(group_name, message)
    logger.info(f"Sent trade update to group {group_name}")

    # Trigger a refresh on the frontend for portfolio and account balance.
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
    Signal handler to update the Portfolio model when a trade is executed.

    If a 'BUY' trade is executed, it creates a new Portfolio position or
    updates an existing one (averaging down). If a 'SELL' trade is executed,
    it reduces the quantity of or closes an existing position. The entire
    operation is wrapped in a database transaction.

    Args:
        sender: The model class that sent the signal (TradeLog).
        instance (TradeLog): The actual instance being saved.
        created (bool): True if a new record was created.
        **kwargs: Wildcard keyword arguments.
    """
    if instance.status != 'EXECUTED':
        return

    logger.info(f"Portfolio update signal triggered for executed trade: {instance.id}")

    try:
        with transaction.atomic():
            if instance.trade_type == 'BUY':
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
                    # Update existing position (average down)
                    old_total_value = portfolio.quantity * portfolio.average_buy_price
                    new_total_value = instance.quantity * instance.price
                    total_quantity = portfolio.quantity + instance.quantity

                    portfolio.average_buy_price = (old_total_value + new_total_value) / total_quantity
                    portfolio.quantity = total_quantity
                    portfolio.save()
                    logger.info(f"Updated portfolio position for {instance.symbol}. New quantity: {total_quantity}")
                else:
                    logger.info(f"Created new portfolio position for {instance.symbol}.")

            elif instance.trade_type == 'SELL':
                try:
                    portfolio = Portfolio.objects.get(account=instance.account, symbol=instance.symbol, is_open=True)

                    if portfolio.quantity > instance.quantity:
                        # Partial sell
                        portfolio.quantity -= instance.quantity
                        portfolio.save()
                        logger.info(f"Partially sold {instance.symbol}. Remaining quantity: {portfolio.quantity}")
                    else:
                        # Full sell, close position
                        portfolio.quantity = 0
                        portfolio.is_open = False
                        portfolio.save()
                        logger.info(f"Fully sold {instance.symbol}. Position closed.")

                except Portfolio.DoesNotExist:
                    logger.error(f"Attempted to sell {instance.symbol}, but no open portfolio position was found for account {instance.account.id}.")

    except Exception as e:
        logger.error(f"Error updating portfolio for trade {instance.id}: {e}", exc_info=True)
