# invest-app/trading/management/commands/test_kis_order.py

from django.core.management.base import BaseCommand, CommandError
from trading.models import TradingAccount
from trading.kis_client import KISApiClient
import json

class Command(BaseCommand):
    help = '지정된 정보로 KIS API를 통해 주식 주문을 테스트합니다.'

    def add_arguments(self, parser):
        parser.add_argument('account_id', type=int, help='API 인증에 사용할 TradingAccount의 ID')
        parser.add_argument('symbol', type=str, help='주문할 종목의 단축 코드 (예: 005930)')
        parser.add_argument('quantity', type=int, help='주문 수량')
        parser.add_argument('price', type=int, help='주문 가격 (지정가: 실제가격, 시장가: 0)')
        parser.add_argument('order_type', type=str, choices=['BUY', 'SELL'], help='주문 유형 (BUY 또는 SELL)')
        # 수정: 시장가/지정가를 선택할 수 있는 옵션 추가
        parser.add_argument('--order_division', type=str, default='00', choices=['00', '01'], help='주문 구분 (00: 지정가, 01: 시장가)')

    def handle(self, *args, **options):
        # ... (이전 코드와 동일) ...
        account_id = options['account_id']
        symbol = options['symbol']
        quantity = options['quantity']
        price = options['price']
        order_type = options['order_type'].upper()
        order_division = options['order_division']
        
        try:
            account = TradingAccount.objects.get(pk=account_id)
            self.stdout.write(self.style.SUCCESS(f"'{account.account_name}' 계좌를 사용하여 주문을 시도합니다."))
        except TradingAccount.DoesNotExist:
            raise CommandError(f'ID가 "{account_id}"인 TradingAccount를 찾을 수 없습니다.')

        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )
        
        order_div_name = "시장가" if order_division == '01' else "지정가"
        self.stdout.write(f"주문 실행: {symbol} {quantity}주, {price}원, {order_type} ({order_div_name})")
        
        # 수정: order_division 인자 전달
        order_response = client.place_order(
            symbol=symbol,
            quantity=quantity,
            price=price,
            order_type=order_type,
            order_division=order_division
        )
        
        if order_response and order_response.get('rt_cd') == '0':
            self.stdout.write(self.style.SUCCESS("✅ 주문이 성공적으로 접수되었습니다!"))
            pretty_json = json.dumps(order_response, indent=4, ensure_ascii=False)
            self.stdout.write(pretty_json)
        else:
            self.stdout.write(self.style.ERROR("🚨 주문 접수에 실패했습니다."))
            if order_response:
                pretty_json = json.dumps(order_response, indent=4, ensure_ascii=False)
                self.stdout.write(pretty_json)