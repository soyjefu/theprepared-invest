# invest-app/trading/risk_management.py

import logging

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self, client, account):
        """
        리스크 관리에 필요한 KIS API 클라이언트와 계좌 정보를 받습니다.
        """
        self.client = client
        self.account = account

    def check_duplicate_position(self, symbol):
        """이미 보유한 종목인지 확인합니다."""
        balance_data = self.client.get_account_balance()
        if balance_data and balance_data.get('rt_cd') == '0':
            owned_stocks = [stock['pdno'] for stock in balance_data.get('output1', [])]
            if symbol in owned_stocks:
                logger.info(f"[{symbol}] 리스크 관리: 실패. 이미 보유 중인 종목입니다.")
                return False # 리스크 관리 실패
        else:
            logger.error(f"[{symbol}] 리스크 관리: 잔고 확인에 실패했습니다.")
            return False # 리스크 관리 실패
        
        logger.info(f"[{symbol}] 리스크 관리: 통과. (중복 포지션 없음)")
        return True # 리스크 관리 통과

    def assess(self, symbol, order_type):
        """
        모든 리스크 규칙을 종합적으로 평가합니다.
        :param symbol: 거래할 종목
        :param order_type: 'BUY' 또는 'SELL'
        :return: 모든 리스크 규칙 통과 시 True, 아니면 False
        """
        if order_type.upper() == 'BUY':
            # 매수 주문의 경우, 중복 포지션 규칙을 확인
            if not self.check_duplicate_position(symbol):
                return False
        
        # TODO: 향후 이곳에 추가적인 리스크 규칙들을 추가 (예: 최대 자본금 대비 주문 금액 확인)
        
        return True