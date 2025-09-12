# invest-app/trading/models.py
from django.db import models
from django.contrib.auth.models import User

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
    symbol = models.CharField(max_length=20, help_text="종목코드")
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


# --- 신규: AI 기반 투자 전략의 설정을 관리할 모델 ---
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator

class StrategySettings(models.Model):
    """AI 투자 전략의 글로벌 설정을 관리하는 싱글톤 모델."""
    short_term_allocation = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="단기 투자 전략에 할당할 자본의 비율(%)"
    )
    mid_term_allocation = models.DecimalField(
        max_digits=5, decimal_places=2, default=40.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="중기 투자 전략에 할당할 자본의 비율(%)"
    )
    long_term_allocation = models.DecimalField(
        max_digits=5, decimal_places=2, default=30.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="장기 투자 전략에 할당할 자본의 비율(%)"
    )
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """세 할당량의 합이 100인지 검증합니다."""
        total_allocation = self.short_term_allocation + self.mid_term_allocation + self.long_term_allocation
        if total_allocation != 100:
            raise ValidationError(f"전체 할당량의 합이 100%가 되어야 합니다. 현재 합계: {total_allocation}%")

    def save(self, *args, **kwargs):
        """이 모델의 인스턴스가 단 하나만 존재하도록 보장합니다."""
        if not self.pk and StrategySettings.objects.exists():
            raise ValidationError("StrategySettings는 단 하나만 존재할 수 있습니다. 기존 설정을 수정해주세요.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"전략 설정 (단기: {self.short_term_allocation}%, 중기: {self.mid_term_allocation}%, 장기: {self.long_term_allocation}%)"

    class Meta:
        verbose_name = "AI 전략 설정"
        verbose_name_plural = "AI 전략 설정"