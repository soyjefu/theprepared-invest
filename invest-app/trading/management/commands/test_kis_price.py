# invest-app/trading/management/commands/test_kis_price.py

from django.core.management.base import BaseCommand, CommandError
from trading.models import TradingAccount
from trading.kis_client import KISApiClient
import json

class Command(BaseCommand):
    help = '지정된 계좌와 종목 코드로 현재가 조회를 테스트합니다.'

    def add_arguments(self, parser):
        parser.add_argument('account_id', type=int, help='API 인증에 사용할 TradingAccount의 ID')
        parser.add_argument('symbol', type=str, help='가격을 조회할 종목의 단축 코드 (예: 005930)')

    def handle(self, *args, **options):
        account_id = options['account_id']
        symbol = options['symbol']
        
        try:
            account = TradingAccount.objects.get(pk=account_id)
            self.stdout.write(self.style.SUCCESS(f"'{account.account_name}' 계좌 정보를 사용하여 인증을 시도합니다."))
        except TradingAccount.DoesNotExist:
            raise CommandError(f'ID가 "{account_id}"인 TradingAccount를 찾을 수 없습니다.')

        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )
        
        self.stdout.write(f"종목코드 '{symbol}'의 현재가 조회를 시도합니다...")
        
        price_info = client.get_current_price(symbol)
        
        if price_info and price_info.get('rt_cd') == '0':
            self.stdout.write(self.style.SUCCESS(f"✅ '{symbol}' 현재가 조회에 성공했습니다!"))
            # 보기 좋게 출력
            pretty_json = json.dumps(price_info, indent=4, ensure_ascii=False)
            self.stdout.write(pretty_json)
        else:
            self.stdout.write(self.style.ERROR("🚨 현재가 조회에 실패했습니다."))
            if price_info:
                pretty_json = json.dumps(price_info, indent=4, ensure_ascii=False)
                self.stdout.write(pretty_json)