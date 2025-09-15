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
    Allows GET and PATCH requests.
    """
    serializer_class = PortfolioUpdateSerializer
    permission_classes = [IsAuthenticated]
    queryset = Portfolio.objects.all()

    def get_queryset(self):
        """
        This view should only return portfolio items belonging to the current user.
        """
        return Portfolio.objects.filter(account__user=self.request.user)

from .kis_client import KISApiClient
from decimal import Decimal

class LiquidateAPIView(APIView):
    """
    API view to handle the 'liquidate' action for a trading account.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, account_id):
        """
        Calculates the amount to sell to reach a target cash percentage
        and places sell orders for profitable, short-term stocks.
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

        # 1. Get current account balance and total value
        balance_res = client.get_account_balance()
        if not balance_res or not balance_res.is_ok():
            return Response({'error': 'Failed to get account balance.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        balance_body = balance_res.get_body()
        total_assets = Decimal(balance_body.get('output2', [{}])[0].get('tot_evlu_amt', '0'))
        current_cash = Decimal(balance_body.get('output2', [{}])[0].get('dnca_tot_amt', '0'))

        # 2. Calculate how much value needs to be sold
        target_cash_value = total_assets * (target_cash_percentage / Decimal(100))
        amount_to_sell = target_cash_value - current_cash

        if amount_to_sell <= 0:
            return Response({'message': 'Current cash percentage already meets or exceeds the target.'}, status=status.HTTP_200_OK)

        # 3. Find suitable stocks to sell
        # Priority: Profitable, short-term stocks.
        # This requires knowing the current price. We will fetch it for each open position.
        open_positions = Portfolio.objects.filter(account=account, is_open=True, quantity__gt=0)

        sell_candidates = []
        for pos in open_positions:
            price_res = client.get_current_price(pos.symbol)
            if price_res and price_res.is_ok():
                current_price = Decimal(price_res.get_body().get('output', {}).get('stck_prpr', '0'))
                if current_price > pos.average_buy_price: # It's profitable
                    profit_margin = (current_price - pos.average_buy_price) / pos.average_buy_price
                    sell_candidates.append({
                        'portfolio': pos,
                        'current_price': current_price,
                        'profit_margin': profit_margin
                    })

        # Sort candidates by short-term first, then by highest profit margin
        sell_candidates.sort(key=lambda x: (
            x['portfolio'].analyzedstock.investment_horizon != 'SHORT', # Puts 'SHORT' first
            -x['profit_margin'] # Sorts by highest profit descending
        ))

        # 4. Place sell orders
        sold_value = Decimal('0')
        orders_placed = []
        for candidate in sell_candidates:
            if sold_value >= amount_to_sell:
                break

            portfolio_item = candidate['portfolio']
            price_to_sell_at = int(candidate['current_price'])

            # Determine how many shares to sell
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
        # We need a client to make API calls for market data
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
