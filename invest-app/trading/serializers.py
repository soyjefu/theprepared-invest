from rest_framework import serializers
from .models import Portfolio

class PortfolioUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating specific fields of a Portfolio item.
    """
    class Meta:
        model = Portfolio
        # Fields that the user is allowed to update via the API
        fields = [
            'stop_loss_price',
            'target_price',
        ]
        # Make fields not required, so PATCH can be used for partial updates
        extra_kwargs = {
            'stop_loss_price': {'required': False},
            'target_price': {'required': False},
        }

class LiquidateSerializer(serializers.Serializer):
    """
    Serializer for the liquidate action.
    Validates the target cash percentage.
    """
    target_cash_percentage = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=0.0,
        max_value=100.0,
        help_text="The desired percentage of total assets to be held in cash."
    )
