from django import forms
from .models import TradingAccount, StrategySettings

class TradingAccountForm(forms.ModelForm):
    """
    A form for creating and updating TradingAccount instances.
    """
    app_secret = forms.CharField(widget=forms.PasswordInput, label="App Secret")

    class Meta:
        """
        Meta options for the TradingAccountForm.
        """
        model = TradingAccount
        fields = ['account_name', 'account_number', 'account_type', 'app_key', 'app_secret', 'is_active']
        labels = {
            'account_name': 'Account Nickname',
            'account_number': 'Account Number (with hyphen)',
            'account_type': 'Account Type',
            'app_key': 'App Key',
            'app_secret': 'App Secret',
            'is_active': 'Enable Automated Trading',
        }
        widgets = {
            'account_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678-01'}),
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'app_key': forms.TextInput(attrs={'class': 'form-control'}),
            'app_secret': forms.PasswordInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class StrategySettingsForm(forms.ModelForm):
    """
    A form for updating the global StrategySettings.
    """
    class Meta:
        model = StrategySettings
        fields = [
            'trading_fee_rate', 'trading_tax_rate',
            'risk_per_trade', 'max_total_risk',
            'dca_base_amount', 'dca_settings_json'
        ]
        widgets = {
            'trading_fee_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.00001'}),
            'trading_tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001'}),
            'risk_per_trade': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.001'}),
            'max_total_risk': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'dca_base_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'dca_settings_json': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
        }
        help_texts = {
            'dca_settings_json': 'Must be in valid JSON format.'
        }
