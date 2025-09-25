import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import TradingAccount

logger = logging.getLogger(__name__)

class DashboardConsumer(AsyncWebsocketConsumer):
    """
    Handles WebSocket connections for real-time dashboard updates.

    This consumer manages subscriptions to various data streams (groups) related
    to a specific trading account and forwards messages from those groups to the
    client. It handles subscriptions for account-wide data, portfolio changes,
    trade updates, and specific stock prices.
    """

    async def connect(self):
        """
        Handles a new WebSocket connection.

        Authenticates the user from the scope, validates the requested account ID,
        and adds the connection to the relevant Channels groups to receive
        real-time updates.
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
        
        self.group_name_account = f"account_{self.account.id}"
        self.group_name_portfolio = f"portfolio_{self.account.id}"
        self.group_name_trades = f"trades_{self.account.id}"

        await self.channel_layer.group_add(self.group_name_account, self.channel_name)
        await self.channel_layer.group_add(self.group_name_portfolio, self.channel_name)
        await self.channel_layer.group_add(self.group_name_trades, self.channel_name)

        await self.accept()
        logger.info(f"User {self.user.username} connected to WebSocket for account {self.account.account_name}.")
        
        await self.send_json_content({
            "type": "system_message",
            "message": "Connected to real-time server."
        })

    async def disconnect(self, close_code):
        """
        Handles a WebSocket disconnection.

        Removes the connection from all associated Channels groups to stop
        sending messages.
        """
        if hasattr(self, 'group_name_account'):
            await self.channel_layer.group_discard(self.group_name_account, self.channel_name)
            await self.channel_layer.group_discard(self.group_name_portfolio, self.channel_name)
            await self.channel_layer.group_discard(self.group_name_trades, self.channel_name)

        logger.info(f"User {self.user.username} disconnected from WebSocket.")

    async def receive(self, text_data):
        """
        Receives messages from the client to manage subscriptions.

        This method allows the client to dynamically subscribe to or unsubscribe
        from real-time price updates for a specific stock symbol.

        Args:
            text_data (str): The JSON-encoded message from the client.
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

    async def account_update(self, event):
        """Handler for messages sent to the 'account' group."""
        await self.send_json_content(event["data"])

    async def portfolio_update(self, event):
        """Handler for messages sent to the 'portfolio' group."""
        await self.send_json_content(event["data"])

    async def trade_update(self, event):
        """Handler for messages sent to the 'trades' group."""
        await self.send_json_content(event["data"])

    async def stock_price_update(self, event):
        """Handler for messages sent to a 'stock_price' group."""
        await self.send_json_content(event["data"])
        
    async def system_message(self, event):
        """Handler for system messages."""
        await self.send_json_content(event["data"])

    async def send_json_content(self, content):
        """
        Helper method to serialize content to JSON and send to the client.

        Args:
            content (dict): The data to send.
        """
        await self.send(text_data=json.dumps(content))

    @database_sync_to_async
    def get_trading_account(self, user: User, account_id: str):
        """
        Fetches a trading account from the database asynchronously.

        This method ensures that the requested account exists and belongs to the
        currently authenticated user.

        Args:
            user (User): The authenticated user.
            account_id (str): The ID of the account to fetch.

        Returns:
            TradingAccount | None: The account instance if found and authorized,
                                  otherwise None.
        """
        try:
            return TradingAccount.objects.get(id=account_id, user=user)
        except TradingAccount.DoesNotExist:
            return None