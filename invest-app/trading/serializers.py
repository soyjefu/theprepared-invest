from decimal import Decimal
from rest_framework import serializers
from .models import Portfolio

class PortfolioUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating risk management fields of a Portfolio item.

    This serializer is used with the `PortfolioDetailAPIView` to allow users
    to modify the `stop_loss_price` and `target_price` of their open positions
    via a PATCH request.
    """
    class Meta:
        """
        Meta options for the PortfolioUpdateSerializer.
        """
        model = Portfolio
        fields = [
            'stop_loss_price',
            'target_price',
        ]
        extra_kwargs = {
            'stop_loss_price': {'required': False},
            'target_price': {'required': False},
        }

class LiquidateSerializer(serializers.Serializer):
    """
    Serializer for validating the input to the liquidate action API.

    It ensures that the `target_cash_percentage` provided by the user is a
    valid decimal between 0 and 100.
    """
    target_cash_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0.0'),
        max_value=Decimal('100.0'),
        help_text="The desired percentage of total assets to be held in cash."
    )
