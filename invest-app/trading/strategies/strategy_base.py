# invest-app/trading/strategies/strategy_base.py

from abc import ABC, abstractmethod
import pandas as pd

class StrategyBase(ABC):
    """
    모든 매매 전략의 기본이 되는 추상 базовый класс입니다.
    모든 전략은 이 클래스를 상속받아 run 메소드를 반드시 구현해야 합니다.
    """
    def __init__(self, client, account, strategy_model, symbol):
        """
        전략 실행에 필요한 객체들을 초기화합니다.
        
        :param client: KISApiClient 인스턴스
        :param account: TradingAccount 모델 인스턴스
        :param strategy_model: Strategy 모델 인스턴스 (DB에 저장된 파라미터 접근용)
        :param symbol: 거래할 종목 코드
        """
        self.client = client
        self.account = account
        self.strategy_model = strategy_model
        self.symbol = symbol
        self.params = strategy_model.parameters # DB에 JSON으로 저장된 파라미터

    @abstractmethod
    def run(self):
        """
        전략의 핵심 로직을 구현하는 메소드입니다.
        이 메소드는 반드시 하위 클래스에서 재정의(override)되어야 합니다.
        """
        raise NotImplementedError("전략의 run 메소드가 구현되지 않았습니다.")

    def _get_price_history_df(self, days=100):
        """
        KISApiClient를 사용하여 일봉 데이터를 가져오고 Pandas DataFrame으로 변환합니다.
        
        :param days: 조회할 기간 (일)
        :return: Pandas DataFrame or None
        """
        history_data = self.client.get_daily_price_history(self.symbol, days=days)
        
        if history_data and history_data.get('rt_cd') == '0':
            df = pd.DataFrame(history_data['output2'])
            # 데이터 가공: 문자열을 숫자형으로 변환하고 날짜를 datetime 객체로 변환
            numeric_cols = ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol']
            for col in numeric_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d')
            df = df.sort_values('stck_bsop_date').reset_index(drop=True)
            return df
            
        return None