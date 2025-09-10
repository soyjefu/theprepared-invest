# trading/consumers.py
import json
import asyncio
import websockets
import logging
from datetime import datetime
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from .trade_logic import get_strategies
from .models import TradingAccount, TradeLog

logger = logging.getLogger(__name__)

class TradeConsumer(AsyncWebsocketConsumer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.kis_ws = None
        self.is_running = False
        self.account_id = None
        self.client = None
        self.account = None # TradingAccount 모델 인스턴스

    async def connect(self):
        self.account_id = self.scope['url_route']['kwargs']['account_id']
        logger.info(f"[{self.account_id}] TradeConsumer 연결 시도.")

        self.account, self.client, _ = await sync_to_async(get_strategies)(self.account_id)
        if not self.client or not self.account:
            logger.error(f"[{self.account_id}] KIS 클라이언트 또는 계좌 정보 초기화 실패. 연결을 종료합니다.")
            await self.close()
            return
        
        await self.accept()
        logger.info(f"[{self.account_id}] 웹소켓 연결 성공.")
        self.is_running = True
        asyncio.create_task(self.run_kis_websocket())

    async def disconnect(self, close_code):
        logger.info(f"[{self.account_id}] TradeConsumer 연결 종료. (코드: {close_code})")
        self.is_running = False
        if self.kis_ws and self.kis_ws.open:
            await self.kis_ws.close()

    @sync_to_async
    def _get_approval_key_sync(self):
        return self.client.get_approval_key()

    async def run_kis_websocket(self):
        uri = "ws://ops.koreainvestment.com:21000" # 실전
        if self.client.is_simulation:
            uri = "ws://ops.koreainvestment.com:31000" # 모의투자
        
        approval_key = await self._get_approval_key_sync()
        if not approval_key:
            logger.error(f"[{self.account_id}] KIS 실시간 접속키 발급 실패. 실시간 연동을 중단합니다.")
            await self.send_error_message("KIS 실시간 접속키 발급에 실패했습니다.")
            return

        reconnect_delay = 1
        while self.is_running:
            try:
                async with websockets.connect(uri, ping_interval=None) as websocket:
                    self.kis_ws = websocket
                    logger.info(f"[{self.account_id}] KIS 웹소켓 서버에 연결되었습니다.")
                    reconnect_delay = 1

                    await self.subscribe_execution_report(approval_key)

                    async for message in websocket:
                        await self.handle_kis_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"[{self.account_id}] KIS 웹소켓 연결이 종료되었습니다: {e}")
            except Exception as e:
                logger.error(f"[{self.account_id}] KIS 웹소켓 처리 중 오류 발생: {e}", exc_info=True)
            
            if self.is_running:
                logger.info(f"[{self.account_id}] {reconnect_delay}초 후 KIS 웹소켓 재연결을 시도합니다.")
                await self.send_system_message(f"KIS 서버와 연결이 끊겼습니다. {reconnect_delay}초 후 재연결합니다.")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)

    async def subscribe_execution_report(self, approval_key):
        tr_id = "H0STCNI9" if self.client.is_simulation else "H0STCNI0"
        # HTS ID 대신 앱키를 사용하도록 KIS 정책이 변경될 수 있으므로, 문서 확인이 필요합니다.
        # 여기서는 기존 로직을 유지합니다.
        user_id = self.account.owner.username 

        subscription_data = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8"
            },
            "body": { "input": { "tr_id": tr_id, "tr_key": user_id } }
        }
        await self.kis_ws.send(json.dumps(subscription_data))
        logger.info(f"[{self.account_id}] 실시간 체결통보 구독 요청 전송: {subscription_data}")
        await self.send_system_message("실시간 체결 정보 수신을 시작합니다.")

    async def handle_kis_message(self, message):
        if message.startswith('0') or message.startswith('1'):
            parts = message.split('|')
            tr_id = parts[1]
            
            if tr_id in ("H0STCNI0", "H0STCNI9"):
                try:
                    # 데이터 파싱
                    decrypted_data = self.client.decrypt_websocket_data(parts[3])
                    execution_data = self.parse_execution_data(decrypted_data)

                    # '체결' 데이터만 DB에 기록
                    if execution_data.get('is_executed'):
                        logger.info(f"[{self.account_id}] 체결통보 수신: {execution_data}")
                        await self.save_trade_log(execution_data)
                        await self.send(text_data=json.dumps({
                            'type': 'execution_report',
                            'data': execution_data
                        }))
                    else:
                        logger.info(f"[{self.account_id}] 주문 접수/거부 통보 수신: {execution_data}")
                        await self.send_system_message(f"주문 접수: {execution_data.get('ticker_name', '알수없는 종목')} {execution_data.get('quantity', 0)}주")
                except Exception as e:
                    logger.error(f"체결 데이터 처리 중 오류: {e}", exc_info=True)
        
        elif message.startswith('{'):
            try:
                msg_data = json.loads(message)
                header = msg_data.get('header', {})
                if header.get('tr_id') == 'PINGPONG':
                    logger.debug(f"[{self.account_id}] KIS PINGPONG 수신.")
                    await self.kis_ws.pong(message.encode('utf-8'))
                else:
                    logger.info(f"[{self.account_id}] KIS 상태 메시지: {msg_data}")
                    await self.send_system_message(f"KIS 서버 메시지: {msg_data.get('body', {}).get('msg1', '알 수 없는 메시지')}")
            except json.JSONDecodeError:
                logger.warning(f"[{self.account_id}] KIS JSON 메시지 파싱 실패: {message}")
        else:
            logger.warning(f"[{self.account_id}] 알 수 없는 KIS 메시지 수신: {message}")

    def parse_execution_data(self, data_str):
        fields = data_str.split('^')
        trade_type_code = fields[10] # 10번째 필드가 매도매수구분코드
        return {
            'account_number': fields[0],
            'order_id': fields[1],
            'ticker': fields[3].strip(),
            'ticker_name': fields[4].strip(),
            'trade_type': "매수" if trade_type_code == '02' else "매도",
            'quantity': int(fields[7]),
            'price': float(fields[8]),
            'is_executed': fields[14] == '2', # 1: 접수/거부, 2: 체결
            'timestamp': fields[19], # HHMMSS
        }

    @database_sync_to_async
    def save_trade_log(self, data):
        try:
            TradeLog.objects.create(
                account=self.account,
                ticker=data['ticker'],
                price=data['price'],
                quantity=data['quantity'],
                trade_type='buy' if data['trade_type'] == '매수' else 'sell',
                order_id=data['order_id'],
            )
            logger.info(f"[{self.account_id}] TradeLog 저장 완료: {data['ticker']} {data['quantity']}주")
        except Exception as e:
            logger.error(f"[{self.account_id}] TradeLog 저장 실패: {e}", exc_info=True)

    async def send_system_message(self, message):
        await self.send(text_data=json.dumps({'type': 'system_message', 'message': message}))

    async def send_error_message(self, message):
        await self.send(text_data=json.dumps({'type': 'error', 'message': message}))