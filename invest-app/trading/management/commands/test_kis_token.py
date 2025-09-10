# invest-app/trading/management/commands/test_kis_token.py

from django.core.management.base import BaseCommand, CommandError
from trading.models import TradingAccount
from trading.kis_client import KISApiClient

class Command(BaseCommand):
    help = '지정된 계좌 ID를 사용하여 KIS API 접근 토큰 발급을 테스트합니다.'

    def add_arguments(self, parser):
        parser.add_argument('account_id', type=int, help='테스트할 TradingAccount의 ID')

    def handle(self, *args, **options):
        account_id = options['account_id']
        
        try:
            account = TradingAccount.objects.get(pk=account_id)
            self.stdout.write(self.style.SUCCESS(f"'{account.account_name}' 계좌 정보를 찾았습니다 (ID: {account.id})."))
        except TradingAccount.DoesNotExist:
            raise CommandError(f'ID가 "{account_id}"인 TradingAccount를 찾을 수 없습니다.')

        if not account.is_active:
            self.stdout.write(self.style.WARNING("계좌가 활성 상태가 아닙니다."))
            return

        # 계좌 종류에 따라 클라이언트 생성
        account_type_map = {
            'SIM': 'virtual',
            'REAL': 'real'
        }
        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_type=account_type_map.get(account.account_type, 'virtual')
        )
        
        self.stdout.write("토큰 발급을 시도합니다...")
        
        token = client.get_access_token()
        
        if token:
            self.stdout.write(self.style.SUCCESS("✅ 토큰 발급에 성공했습니다!"))
            self.stdout.write(f"Access Token: {token[:30]}...") # 토큰 일부만 출력
        else:
            self.stdout.write(self.style.ERROR("🚨 토큰 발급에 실패했습니다. kis_client.py의 로그를 확인해주세요."))