import logging
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from trading.models import TradingAccount, HistoricalPriceData, AnalyzedStock
from trading.kis_client import KISApiClient
from decimal import Decimal

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Populates the database with historical price data for specified stocks.'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='The username to use for API credentials.')
        parser.add_argument('--symbols', nargs='+', type=str, help='A list of stock symbols to fetch data for. If not provided, it will use all symbols from AnalyzedStock.')
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
            symbols = list(AnalyzedStock.objects.filter(is_investable=True).values_list('symbol', flat=True))
            self.stdout.write(self.style.SUCCESS(f"Found {len(symbols)} investable stocks to process."))

        # 백테스팅에 필수적인 코스피 지수 데이터를 항상 포함
        if '0001' not in symbols:
            symbols.append('0001')

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_to_fetch)

        for symbol in symbols:
            self.stdout.write(f"Fetching historical data for {symbol}...")

            try:
                all_price_data = []
                # KIS API는 한번에 100일치 데이터만 조회 가능하므로, 기간을 나누어 요청
                temp_end_date = end_date
                while temp_end_date > start_date:
                    temp_start_date = max(start_date, temp_end_date - timedelta(days=99))
                    self.stdout.write(f"  - Fetching period: {temp_start_date.strftime('%Y-%m-%d')} to {temp_end_date.strftime('%Y-%m-%d')}")

                    fetch_func = client.get_daily_price_history if symbol != '0001' else client.get_index_price_history
                    res = fetch_func(symbol, days=(temp_end_date - temp_start_date).days)

                    if res and res.is_ok():
                        price_list = res.get_body().get('output2', [])
                        all_price_data.extend(price_list)
                    else:
                        self.stdout.write(self.style.WARNING(f"    - Could not fetch data for period. Response: {res.text if res else 'No Response'}"))

                    temp_end_date = temp_start_date - timedelta(days=1)

                price_list = all_price_data

                data_to_create = []
                for item in price_list:
                    # 'stck_bsop_date' 키가 있는지 확인
                    if 'stck_bsop_date' not in item:
                        logger.warning(f"Skipping item for {symbol} due to missing 'stck_bsop_date': {item}")
                        continue

                    data_to_create.append(
                        HistoricalPriceData(
                            symbol=symbol,
                            date=datetime.strptime(item['stck_bsop_date'], '%Y%m%d').date(),
                            open_price=Decimal(item.get('stck_oprc', '0')),
                            high_price=Decimal(item.get('stck_hgpr', '0')),
                            low_price=Decimal(item.get('stck_lwpr', '0')),
                            close_price=Decimal(item.get('stck_clpr', '0')),
                            volume=int(item.get('acml_vol', '0'))
                        )
                    )

                # 중복을 무시하고 대량 생성 (ignore_conflicts=True)
                HistoricalPriceData.objects.bulk_create(data_to_create, ignore_conflicts=True)
                self.stdout.write(self.style.SUCCESS(f"Successfully populated {len(data_to_create)} records for {symbol}."))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"An error occurred while processing {symbol}: {e}"))

        self.stdout.write(self.style.SUCCESS("Historical data population complete."))