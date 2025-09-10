# invest-app/trading/management/commands/test_kis_balance.py

from django.core.management.base import BaseCommand, CommandError
from trading.models import TradingAccount
from trading.kis_client import KISApiClient
import json

class Command(BaseCommand):
    help = '지정된 계좌 ID의 잔고를 조회하여 KIS API 연동을 테스트합니다.'

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
        
        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type # 수정: DB에 저장된 계좌 타입을 직접 전달
        )
        
        self.stdout.write("계좌 잔고 조회를 시도합니다...")
        
        balance_info = client.get_account_balance()
        
        # 수정: API 응답 코드를 확인하고, 실패 시 상세 내용 출력
        if balance_info and balance_info.get('rt_cd') == '0':
            self.stdout.write(self.style.SUCCESS("✅ 계좌 잔고 조회에 성공했습니다!"))
            pretty_json = json.dumps(balance_info, indent=4, ensure_ascii=False)
            self.stdout.write(pretty_json)
        else:
            self.stdout.write(self.style.ERROR("🚨 계좌 잔고 조회에 실패했습니다."))
            if balance_info:
                # 실패 시 서버가 보낸 원본 메시지 출력
                pretty_json = json.dumps(balance_info, indent=4, ensure_ascii=False)
                self.stdout.write(pretty_json)