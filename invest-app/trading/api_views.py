from rest_framework import generics, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Portfolio, TradingAccount
from .serializers import PortfolioUpdateSerializer, LiquidateSerializer

class PortfolioDetailAPIView(generics.RetrieveUpdateAPIView):
    """
    API view to retrieve or update a specific portfolio item.

    Allows GET requests to retrieve the details of a portfolio item and
    PATCH requests to update its mutable fields, such as 'stop_loss_price'
    and 'target_price'. Ensures that users can only access their own
    portfolio items.
    """
    serializer_class = PortfolioUpdateSerializer
    permission_classes = [IsAuthenticated]
    queryset = Portfolio.objects.all()

    def get_queryset(self):
        """
        Filters the queryset to only include portfolio items belonging to the
        currently authenticated user.
        """
        return Portfolio.objects.filter(account__user=self.request.user)

from .kis_client import KISApiClient
from decimal import Decimal

class LiquidateAPIView(APIView):
    """
    API view to handle the 'liquidate' action for a trading account.

    This view provides a POST endpoint that allows a user to automatically
    sell assets to reach a specified cash percentage in their account.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, account_id):
        """
        Executes the liquidation process.

        It calculates the total value of assets to sell based on the user's
        `target_cash_percentage`. It then prioritizes selling profitable,
        short-term stocks until the target is met.

        Args:
            request: The HttpRequest object, containing the target percentage.
            account_id (int): The ID of the TradingAccount to liquidate.

        Returns:
            A Response object summarizing the actions taken, including the
            total value sold and a list of placed orders.
        """
        account = get_object_or_404(TradingAccount, id=account_id, user=request.user)
        serializer = LiquidateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        target_cash_percentage = serializer.validated_data['target_cash_percentage']

        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )

        balance_res = client.get_account_balance()
        if not balance_res or not balance_res.is_ok():
            return Response({'error': 'Failed to get account balance.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        balance_body = balance_res.get_body()
        total_assets = Decimal(balance_body.get('output2', [{}])[0].get('tot_evlu_amt', '0'))
        current_cash = Decimal(balance_body.get('output2', [{}])[0].get('dnca_tot_amt', '0'))

        target_cash_value = total_assets * (target_cash_percentage / Decimal(100))
        amount_to_sell = target_cash_value - current_cash

        if amount_to_sell <= 0:
            return Response({'message': 'Current cash percentage already meets or exceeds the target.'}, status=status.HTTP_200_OK)

        open_positions = Portfolio.objects.filter(account=account, is_open=True, quantity__gt=0)

        sell_candidates = []
        for pos in open_positions:
            price_res = client.get_current_price(pos.symbol)
            if price_res and price_res.is_ok():
                current_price = Decimal(price_res.get_body().get('output', {}).get('stck_prpr', '0'))
                if current_price > pos.average_buy_price:
                    profit_margin = (current_price - pos.average_buy_price) / pos.average_buy_price
                    sell_candidates.append({
                        'portfolio': pos,
                        'current_price': current_price,
                        'profit_margin': profit_margin
                    })

        sell_candidates.sort(key=lambda x: (
            x['portfolio'].analyzedstock.investment_horizon != 'SHORT',
            -x['profit_margin']
        ))

        sold_value = Decimal('0')
        orders_placed = []
        for candidate in sell_candidates:
            if sold_value >= amount_to_sell:
                break

            portfolio_item = candidate['portfolio']
            price_to_sell_at = int(candidate['current_price'])

            value_of_position = portfolio_item.quantity * price_to_sell_at
            remaining_to_sell = amount_to_sell - sold_value

            if value_of_position <= remaining_to_sell:
                quantity_to_sell = portfolio_item.quantity
            else:
                quantity_to_sell = int(remaining_to_sell // price_to_sell_at)

            if quantity_to_sell == 0:
                continue

            order_response = client.place_order(
                account=account,
                symbol=portfolio_item.symbol,
                quantity=quantity_to_sell,
                price=price_to_sell_at,
                order_type='SELL'
            )

            if order_response and order_response.get('rt_cd') == '0':
                sold_value += quantity_to_sell * price_to_sell_at
                orders_placed.append({
                    'symbol': portfolio_item.symbol,
                    'quantity': quantity_to_sell,
                    'price': price_to_sell_at
                })

        return Response({
            'message': f'Successfully placed {len(orders_placed)} sell orders to liquidate assets.',
            'total_sold_value': sold_value,
            'orders': orders_placed
        }, status=status.HTTP_200_OK)

from . import ai_analysis_service

class AIRecommendationAPIView(APIView):
    """
    Provides AI-based recommendations for market trend and strategy allocation.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to provide AI-driven market analysis.

        This method uses the AI analysis service to determine the current
        market trend (e.g., 'BULL', 'BEAR') and suggests a corresponding
        capital allocation strategy across different investment horizons.

        Args:
            request: The HttpRequest object.

        Returns:
            A Response object containing the market trend and recommended
            allocations.
        """
        account = TradingAccount.objects.filter(user=request.user, is_active=True).first()
        if not account:
            return Response({'error': 'An active trading account is required for AI analysis.'}, status=status.HTTP_400_BAD_REQUEST)

        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )

        market_trend = ai_analysis_service.get_market_trend(client)
        allocations = ai_analysis_service.recommend_strategy_allocations(market_trend)

        response_data = {
            'market_trend': market_trend,
            'recommended_allocations': allocations
        }

        return Response(response_data, status=status.HTTP_200_OK)

class SellPositionAPIView(APIView):
    """
    API view to sell an entire position for a given portfolio item.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """
        Executes the sell order for the entire quantity of a portfolio item.
        """
        portfolio_item = get_object_or_404(Portfolio, pk=pk, account__user=request.user, is_open=True)
        account = portfolio_item.account

        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )

        price_res = client.get_current_price(portfolio_item.symbol)
        if not price_res or not price_res.is_ok():
            return Response({'error': f"Failed to get current price for {portfolio_item.stock_name}."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        current_price = int(price_res.get_body().get('output', {}).get('stck_prpr', '0'))

        if portfolio_item.quantity > 0:
            order_response = client.place_order(
                account=account,
                symbol=portfolio_item.symbol,
                quantity=portfolio_item.quantity,
                price=current_price,
                order_type='SELL'
            )

            if order_response and order_response.get('rt_cd') == '0':
                return Response({'message': f"Sell order for {portfolio_item.stock_name} placed successfully."}, status=status.HTTP_200_OK)
            else:
                error_msg = order_response.get('msg1', 'Unknown error')
                return Response({'error': f"Failed to place sell order: {error_msg}"}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': "No quantity to sell."}, status=status.HTTP_400_BAD_REQUEST)
