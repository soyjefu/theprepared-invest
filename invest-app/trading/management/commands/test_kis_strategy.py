# invest-app/trading/management/commands/test_kis_strategy.py

from django.core.management.base import BaseCommand, CommandError
from trading.models import AccountStrategy
from trading.strategy_handler import run_strategy
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class Command(BaseCommand):
    help = '지정된 전략을 실행하여 매매 신호를 테스트합니다. (리스크 관리 포함)'

    def add_arguments(self, parser):
        parser.add_argument('account_id', type=int, help='API 인증에 사용할 TradingAccount의 ID')
        parser.add_argument('strategy_name', type=str, help='실행할 전략의 이름 (예: golden_cross)')
        parser.add_argument('symbol', type=str, help='전략을 적용할 종목의 단축 코드 (예: 005930)')
        # 수정: --force 옵션 추가
        parser.add_argument('--force', action='store_true', help='장운영 시간 확인을 건너뛰고 강제로 전략을 실행합니다.')

    def handle(self, *args, **options):
        account_id = options['account_id']
        strategy_name = options['strategy_name']
        symbol = options['symbol']
        force_run = options['force'] # 수정: force 옵션 값 가져오기
        
        try:
            acc_strategy = AccountStrategy.objects.get(
                account__id=account_id,
                strategy__name=strategy_name
            )
            self.stdout.write(self.style.SUCCESS(f"계좌: '{acc_strategy.account.account_name}', 전략: '{acc_strategy.strategy.name}'에 대한 테스트를 시작합니다."))
        except AccountStrategy.DoesNotExist:
            raise CommandError(f"ID가 '{account_id}'인 계좌와 이름이 '{strategy_name}'인 전략의 연결(AccountStrategy)을 찾을 수 없습니다.")
        except AccountStrategy.MultipleObjectsReturned:
             raise CommandError(f"ID가 '{account_id}'인 계좌와 이름이 '{strategy_name}'인 전략에 대한 연결이 여러 개 존재합니다.")

        self.stdout.write(f"'{strategy_name}' 전략 핸들러를 종목코드 '{symbol}'에 대해 실행합니다...")
        
        # 수정: force_run 값을 핸들러에 전달
        run_strategy(acc_strategy.id, symbol, force_run=force_run)
        
        self.stdout.write(self.style.SUCCESS("전략 핸들러 실행이 완료되었습니다."))