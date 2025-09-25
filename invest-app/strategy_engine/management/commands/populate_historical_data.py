import logging
import time
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from trading.models import TradingAccount
from trading.kis_client import KISApiClient
from strategy_engine.models import HistoricalPrice
from trading.models import AnalyzedStock # To get the list of stocks
from decimal import Decimal

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Populates the database with historical price data for specified stocks.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username to use for API credentials.')
        parser.add_argument('--symbols', nargs='+', type=str, help='A list of stock symbols to fetch. If not provided, it will use all symbols from AnalyzedStock.')
        parser.add_argument('--days', type=int, default=3650, help='Number of days of historical data to fetch (default: 3650, approx. 10 years).')

    def handle(self, *args, **options):
        username = options['username']
        symbols = options['symbols']
        days_to_fetch = options['days']

        try:
            user = User.objects.get(username=username)
            account = TradingAccount.objects.filter(user=user, is_active=True).first()
            if not account:
                self.stdout.write(self.style.ERROR(f"No active trading account found for user '{username}'."))
                return

            client = KISApiClient(
                app_key=account.app_key,
                app_secret=account.app_secret,
                account_no=account.account_number,
                account_type=account.get_account_type_display()
            )
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"User '{username}' not found."))
            return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Failed to initialize KIS API client: {e}"))
            return

        if not symbols:
            symbols = list(AnalyzedStock.objects.values_list('symbol', flat=True).distinct())
            self.stdout.write(self.style.SUCCESS(f"Found {len(symbols)} unique stocks in AnalyzedStock to process."))

        # 백테스팅에 필수적인 코스피 지수 데이터를 항상 포함 (U.001 형태가 KIS API 업종/지수 조회 표준)
        if '0001' not in symbols:
            symbols.append('0001')

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_to_fetch)

        for symbol in symbols:
            self.stdout.write(f"Fetching historical data for {symbol}...")
            try:
                # KIS API는 한번에 100일치 데이터만 조회 가능하므로, 기간을 나누어 요청
                # API 호출 사이에 딜레이를 주어 안정성 확보
                is_index = symbol == '0001'
                all_price_data = self._fetch_paginated_history(client, symbol, start_date, end_date, is_index)

                if not all_price_data:
                    self.stdout.write(self.style.WARNING(f"No data fetched for {symbol}. Skipping database population."))
                    continue

                data_to_create = []
                for item in all_price_data:
                    date_str = item.get('stck_bsop_date')
                    if not date_str:
                        logger.warning(f"Skipping item for {symbol} due to missing 'stck_bsop_date': {item}")
                        continue

                    # 지수와 일반 종목의 거래량 필드 이름이 다름
                    volume_key = 'acml_tr_pbmn' if is_index else 'acml_vol'

                    data_to_create.append(
                        HistoricalPrice(
                            symbol=symbol,
                            date=datetime.strptime(date_str, '%Y%m%d').date(),
                            open_price=Decimal(item.get('stck_oprc', '0')),
                            high_price=Decimal(item.get('stck_hgpr', '0')),
                            low_price=Decimal(item.get('stck_lwpr', '0')),
                            close_price=Decimal(item.get('stck_clpr', '0')),
                            volume=int(item.get(volume_key, '0'))
                        )
                    )

                # 중복을 무시하고 대량 생성 (ignore_conflicts=True)
                HistoricalPrice.objects.bulk_create(data_to_create, ignore_conflicts=True)
                self.stdout.write(self.style.SUCCESS(f"Successfully populated {len(data_to_create)} records for {symbol}."))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"An error occurred while processing {symbol}: {e}"))
                logger.error(f"Error details for {symbol}:", exc_info=True)

        self.stdout.write(self.style.SUCCESS("Historical data population complete."))

    def _fetch_paginated_history(self, client, symbol, start_date, end_date, is_index):
        """
        Paginates through the KIS API to fetch historical data for a long period.
        """
        all_data = []
        current_end = end_date

        while current_end > start_date:
            # KIS API는 한번에 100일치 데이터만 조회 가능
            current_start = max(start_date, current_end - timedelta(days=99))
            self.stdout.write(f"  - Fetching period: {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")

            fetch_func = client.get_index_price_history if is_index else client.get_daily_price_history

            # get_daily_price_history expects days, not start/end date in its current form in kis_client
            # We will pass the symbol and days.
            days_diff = (current_end - current_start).days + 1
            res = fetch_func(symbol=symbol, days=days_diff) # Note: This might need adjustment if the client function changes

            if res and res.is_ok():
                price_list = res.get_body().get('output2', [])
                # API가 요청 기간 내의 데이터만 반환하도록 필터링 (KIS API가 가끔 요청 기간보다 더 많이 줄 수 있음)
                filtered_list = [p for p in price_list if current_start.strftime('%Y%m%d') <= p['stck_bsop_date'] <= current_end.strftime('%Y%m%d')]
                all_data.extend(filtered_list)
            else:
                error_msg = res.text if res else 'No Response'
                self.stdout.write(self.style.WARNING(f"    - Could not fetch data for period. Response: {error_msg}"))

            current_end = current_start - timedelta(days=1)
            time.sleep(0.2) # API 호출 제한을 피하기 위한 딜레이

        # 중복 제거 및 날짜순 정렬
        unique_data = {item['stck_bsop_date']: item for item in all_data}
        return sorted(unique_data.values(), key=lambda x: x['stck_bsop_date'])