# invest-app/trading/models.py
from django.db import models
from django.contrib.auth.models import User

#
# 1. 거래 계좌 모델
# KIS API 사용에 필요한 계좌 정보와 키를 관리합니다.
#
class TradingAccount(models.Model):
    class AccountType(models.TextChoices):
        SIMULATED = 'SIM', '모의투자'
        REAL = 'REAL', '실전투자'

    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="사용자")
    account_name = models.CharField(max_length=100, help_text="계좌 별칭")
    account_number = models.CharField(max_length=20, unique=True, help_text="계좌번호")
    account_type = models.CharField(
        max_length=4, # 수정: 'REAL'을 저장하기 위해 길이를 4로 변경
        choices=AccountType.choices,
        default=AccountType.SIMULATED,
        help_text="계좌 종류 (모의/실전)"
    )
    brokerage = models.CharField(max_length=50, default="한국투자증권", help_text="증권사")
    app_key = models.CharField(max_length=255, help_text="API Key")
    app_secret = models.CharField(max_length=255, help_text="API Secret")
    is_active = models.BooleanField(default=True, help_text="활성화 여부")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.account_name} ({self.get_account_type_display()})"

#
# 2. 매매 전략 모델
# 시스템에서 사용할 수 있는 매매 전략의 종류와 설정을 정의합니다.
#
class Strategy(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="전략 이름")
    description = models.TextField(blank=True, help_text="전략 설명")
    parameters = models.JSONField(default=dict, help_text="전략 실행에 필요한 파라미터 (e.g., {'short_ma': 5, 'long_ma': 20})")
    is_active = models.BooleanField(default=True, help_text="활성화 여부")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

#
# 3. 계좌별 전략 설정 모델 (연결 테이블)
# 특정 계좌에 어떤 전략을, 얼마의 자본으로 할당할지 설정합니다.
#
class AccountStrategy(models.Model):
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='strategies')
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='accounts')
    is_active = models.BooleanField(default=True, help_text="해당 계좌에서 이 전략의 활성화 여부")
    trading_capital = models.DecimalField(max_digits=15, decimal_places=2, help_text="이 전략에 할당된 자본금")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('account', 'strategy') # 계좌와 전략의 조합은 유일해야 함

    def __str__(self):
        return f"{self.account.account_name} - {self.strategy.name}"

#
# 4. 거래 로그 모델
# 모든 매매 주문 및 체결 내역을 기록합니다.
#
class TradeLog(models.Model):
    class TradeType(models.TextChoices):
        BUY = 'BUY', '매수'
        SELL = 'SELL', '매도'

    class TradeStatus(models.TextChoices):
        PENDING = 'PENDING', '대기'
        EXECUTED = 'EXECUTED', '체결'
        FAILED = 'FAILED', '실패'
        CANCELED = 'CANCELED', '취소'

    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='trade_logs')
    strategy = models.ForeignKey(Strategy, on_delete=models.SET_NULL, null=True, blank=True, help_text="거래에 사용된 전략")
    symbol = models.CharField(max_length=20, help_text="종목코드")
    order_id = models.CharField(max_length=100, unique=True, help_text="주문 ID")
    trade_type = models.CharField(max_length=4, choices=TradeType.choices)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=10, choices=TradeStatus.choices, default=TradeStatus.PENDING)
    timestamp = models.DateTimeField(auto_now_add=True)
    log_message = models.TextField(blank=True, help_text="거래 관련 상세 메시지 또는 에러 로그")

    def __str__(self):
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.account.account_name} - {self.symbol} {self.get_trade_type_display()} ({self.status})"