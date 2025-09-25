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
        """
        Meta options for the StrategySettingsForm.
        """
        model = StrategySettings
        fields = ['short_term_allocation', 'mid_term_allocation', 'long_term_allocation']
        labels = {
            'short_term_allocation': 'Short-Term Allocation (%)',
            'mid_term_allocation': 'Mid-Term Allocation (%)',
            'long_term_allocation': 'Long-Term Allocation (%)',
        }
        widgets = {
            'short_term_allocation': forms.NumberInput(attrs={'class': 'form-control'}),
            'mid_term_allocation': forms.NumberInput(attrs={'class': 'form-control'}),
            'long_term_allocation': forms.NumberInput(attrs={'class': 'form-control'}),
        }
