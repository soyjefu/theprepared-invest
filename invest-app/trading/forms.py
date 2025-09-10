from django import forms
from .models import TradingAccount, StrategySettings

class TradingAccountForm(forms.ModelForm):
    """TradingAccount 모델을 위한 입력 폼"""
    
    # 비밀번호처럼 보이지 않도록 app_secret 필드를 PasswordInput으로 변경
    app_secret = forms.CharField(widget=forms.PasswordInput, label="App Secret")

    class Meta:
        model = TradingAccount
        fields = ['name', 'account_number', 'app_key', 'app_secret', 'is_active', 'is_mock']
        labels = {
            'name': '계좌 별명',
            'account_number': '계좌번호 (하이픈 포함)',
            'app_key': 'App Key',
            'app_secret': 'App Secret',
            'is_active': '자동매매 활성화',
            'is_mock': '모의투자 계좌',
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '12345678-01'}),
            'app_key': forms.TextInput(attrs={'class': 'form-control'}),
            'app_secret': forms.PasswordInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_mock': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class StrategySettingsForm(forms.ModelForm):
    """StrategySettings 모델을 위한 입력 폼"""
    class Meta:
        model = StrategySettings
        # account 필드는 시스템이 자동으로 처리하므로, 사용자가 직접 입력하지 않습니다.
        exclude = ['account']
