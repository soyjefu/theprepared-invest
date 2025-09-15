import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import TradingAccount

logger = logging.getLogger(__name__)

class DashboardConsumer(AsyncWebsocketConsumer):
    """
    Handles WebSocket connections for the main dashboard and other pages.
    This consumer manages subscriptions to different data streams (groups)
    and forwards messages from those groups to the client.
    """

    async def connect(self):
        """
        Handles a new WebSocket connection.
        Authenticates the user, finds their trading account, and adds them
        to relevant channels groups to receive real-time updates.
        """
        self.user = self.scope["user"]
        if not self.user or not self.user.is_authenticated:
            logger.warning("Unauthenticated user tried to connect to WebSocket.")
            await self.close()
            return

        self.account_id = self.scope['url_route']['kwargs']['account_id']
        self.account = await self.get_trading_account(self.user, self.account_id)

        if not self.account:
            logger.warning(f"User {self.user.username} tried to connect with invalid account_id {self.account_id}.")
            await self.close()
            return
        
        # Define group names
        self.group_name_account = f"account_{self.account.id}"
        self.group_name_portfolio = f"portfolio_{self.account.id}"
        self.group_name_trades = f"trades_{self.account.id}"

        # Join relevant groups
        await self.channel_layer.group_add(self.group_name_account, self.channel_name)
        await self.channel_layer.group_add(self.group_name_portfolio, self.channel_name)
        await self.channel_layer.group_add(self.group_name_trades, self.channel_name)

        await self.accept()
        logger.info(f"User {self.user.username} connected to WebSocket for account {self.account.account_name}.")
        
        # Optional: Send a confirmation message to the client
        await self.send_json_content({
            "type": "system_message",
            "message": "실시간 서버에 연결되었습니다."
        })

    async def disconnect(self, close_code):
        """
        Handles a WebSocket disconnection.
        Removes the user from all associated channels groups.
        """
        if hasattr(self, 'group_name_account'):
            await self.channel_layer.group_discard(self.group_name_account, self.channel_name)
            await self.channel_layer.group_discard(self.group_name_portfolio, self.channel_name)
            await self.channel_layer.group_discard(self.group_name_trades, self.channel_name)

        logger.info(f"User {self.user.username} disconnected from WebSocket.")

    async def receive(self, text_data):
        """
        Receives messages from the client.
        This can be used to manage subscriptions, e.g., subscribing to real-time
        prices for a specific stock.
        """
        data = json.loads(text_data)
        message_type = data.get("type")

        logger.info(f"Received message from {self.user.username}: {data}")

        if message_type == "subscribe_stock":
            symbol = data.get("symbol")
            if symbol:
                await self.channel_layer.group_add(f"stock_price_{symbol}", self.channel_name)
                logger.info(f"User {self.user.username} subscribed to stock {symbol}.")

        elif message_type == "unsubscribe_stock":
            symbol = data.get("symbol")
            if symbol:
                await self.channel_layer.group_discard(f"stock_price_{symbol}", self.channel_name)
                logger.info(f"User {self.user.username} unsubscribed from stock {symbol}.")

    # Handler for messages sent to the 'account' group
    async def account_update(self, event):
        await self.send_json_content(event["data"])

    # Handler for messages sent to the 'portfolio' group
    async def portfolio_update(self, event):
        await self.send_json_content(event["data"])

    # Handler for messages sent to the 'trades' group
    async def trade_update(self, event):
        await self.send_json_content(event["data"])

    # Handler for messages sent to the 'stock_price' group
    async def stock_price_update(self, event):
        await self.send_json_content(event["data"])
        
    async def system_message(self, event):
        await self.send_json_content(event["data"])

    async def send_json_content(self, content):
        """Helper to send JSON data to the client."""
        await self.send(text_data=json.dumps(content))

    @database_sync_to_async
    def get_trading_account(self, user: User, account_id: str):
        """
        Fetches the trading account from the database asynchronously.
        Ensures the account belongs to the logged-in user.
        """
        try:
            return TradingAccount.objects.get(id=account_id, user=user)
        except TradingAccount.DoesNotExist:
            return None