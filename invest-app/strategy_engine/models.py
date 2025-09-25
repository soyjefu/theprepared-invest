from django.db import models

class HistoricalPrice(models.Model):
    """
    백테스팅을 위한 종목별 과거 시세 데이터를 저장하는 모델.
    """
    symbol = models.CharField(max_length=20, db_index=True, help_text="종목 코드")
    date = models.DateField(db_index=True, help_text="날짜")
    open_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="시가")
    high_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="고가")
    low_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="저가")
    close_price = models.DecimalField(max_digits=12, decimal_places=2, help_text="종가")
    volume = models.BigIntegerField(help_text="거래량")

    class Meta:
        verbose_name = "과거 시세 데이터"
        verbose_name_plural = "과거 시세 데이터"
        unique_together = ('symbol', 'date') # 종목과 날짜의 조합은 유일해야 함
        ordering = ['-date']

    def __str__(self):
        return f"{self.symbol} - {self.date}"