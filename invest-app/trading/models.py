# invest-app/trading/models.py
from django.db import models
from django.contrib.auth.models import User

# TradingAccount, Strategy, AccountStrategy 모델은 이전과 동일
class TradingAccount(models.Model):
    class AccountType(models.TextChoices):
        SIMULATED = 'SIM', '모의투자'
        REAL = 'REAL', '실전투자'
    user = models.ForeignKey(User, on_delete=models.CASCADE, help_text="사용자")
    account_name = models.CharField(max_length=100, help_text="계좌 별칭")
    account_number = models.CharField(max_length=20, unique=True, help_text="계좌번호")
    account_type = models.CharField(max_length=4, choices=AccountType.choices, default=AccountType.SIMULATED, help_text="계좌 종류 (모의/실전)")
    brokerage = models.CharField(max_length=50, default="한국투자증권", help_text="증권사")
    app_key = models.CharField(max_length=255, help_text="API Key")
    app_secret = models.CharField(max_length=255, help_text="API Secret")
    is_active = models.BooleanField(default=True, help_text="활성화 여부")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return f"{self.user.username} - {self.account_name} ({self.get_account_type_display()})"

class Strategy(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="전략 이름")
    description = models.TextField(blank=True, help_text="전략 설명")
    parameters = models.JSONField(default=dict, blank=True, help_text="전략 실행에 필요한 파라미터 (e.g., {'short_ma': 5, 'long_ma': 20})")
    is_active = models.BooleanField(default=True, help_text="활성화 여부")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self): return self.name

class AccountStrategy(models.Model):
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='strategies')
    strategy = models.ForeignKey(Strategy, on_delete=models.CASCADE, related_name='accounts')
    is_active = models.BooleanField(default=True, help_text="해당 계좌에서 이 전략의 활성화 여부")
    trading_capital = models.DecimalField(max_digits=15, decimal_places=2, help_text="이 전략에 할당된 자본금")
    updated_at = models.DateTimeField(auto_now=True)
    class Meta: unique_together = ('account', 'strategy')
    def __str__(self): return f"{self.account.account_name} - {self.strategy.name}"

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
    # 수정: 주문 실패 시 'FAILED'와 같은 ID가 중복될 수 있으므로 unique 제약 제거
    order_id = models.CharField(max_length=100, help_text="주문 ID") 
    trade_type = models.CharField(max_length=4, choices=TradeType.choices)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=10, choices=TradeStatus.choices, default=TradeStatus.PENDING)
    timestamp = models.DateTimeField(auto_now_add=True)
    log_message = models.TextField(blank=True, help_text="거래 관련 상세 메시지 또는 에러 로그")
    def __str__(self): return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {self.account.account_name} - {self.symbol} {self.get_trade_type_display()} ({self.status})"

# --- 신규: 분석된 종목 정보를 저장할 모델 ---
class AnalyzedStock(models.Model):
    class Horizon(models.TextChoices):
        SHORT = 'SHORT', '단기'
        MID = 'MID', '중기'
        LONG = 'LONG', '장기'
        NONE = 'NONE', '미분류'

    symbol = models.CharField(max_length=20, unique=True, help_text="종목코드")
    stock_name = models.CharField(max_length=100, help_text="종목명")
    is_investable = models.BooleanField(default=False, help_text="1차 분석(투자가치) 통과 여부")
    investment_horizon = models.CharField(
        max_length=5, choices=Horizon.choices, default=Horizon.NONE,
        help_text="2차 분석(투자 기간) 결과"
    )
    analysis_date = models.DateField(auto_now=True, help_text="분석이 수행된 날짜")
    last_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="분석 시점의 현재가")
    raw_analysis_data = models.JSONField(default=dict, blank=True, help_text="분석에 사용된 원본 데이터 (재무비율 등)")

    def __str__(self):
        return f"[{self.symbol}] {self.stock_name} ({self.get_investment_horizon_display()})"

# --- 신규: 현재 보유 종목의 상태와 리스크 기준을 관리할 모델 ---
class Portfolio(models.Model):
    account = models.ForeignKey(TradingAccount, on_delete=models.CASCADE, related_name='portfolio_items')
    symbol = models.CharField(max_length=20, help_text="종목코드")
    stock_name = models.CharField(max_length=100, help_text="종목명")
    quantity = models.PositiveIntegerField(help_text="보유 수량")
    average_buy_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="평균 매수 단가")
    
    # 리스크 관리 기준
    stop_loss_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="손절매 가격")
    target_price = models.DecimalField(max_digits=15, decimal_places=2, help_text="목표(익절) 가격")

    is_open = models.BooleanField(default=True, help_text="현재 보유 중인 포지션 여부")
    entry_log = models.ForeignKey(TradeLog, on_delete=models.SET_NULL, null=True, related_name='portfolio_entry')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ('account', 'symbol', 'is_open') # 한 계좌에 동일 종목의 오픈 포지션은 하나만 존재

    def __str__(self):
        status = "OPEN" if self.is_open else "CLOSED"
        return f"[{self.account.account_name}] {self.symbol}: {self.quantity}주 @{self.average_buy_price} ({status})"