# invest-app/trading/analysis.py

from datetime import date, timedelta
from decimal import Decimal
from .models import AnalyzedStock, Portfolio, TradingAccount
from .kis_client import KISClient  # 가상의 한국투자증권 API 클라이언트
# from .ai_model_handler import AIModelHandler # 가상의 AI 모델 핸들러

# --- 1차 분석: 투자가치 높은 종목 스크리닝 ---
def screen_investable_stocks():
    """
    1. 전체 주식 시장의 종목 리스트를 가져옵니다.
    2. AI와 통계 기반으로 투자가치가 없거나 위험도가 높은 종목을 필터링합니다.
    3. 1차 분석을 통과한 종목들을 AnalyzedStock 모델에 저장/업데이트합니다.
    """
    print("--- 1차 분석: 종목 스크리닝 시작 ---")
    
    # kis_client = KISClient()
    # all_symbols = kis_client.get_all_stock_symbols() # 예시: 전체 종목 코드 가져오기
    
    # 임시 테스트용 종목 리스트
    all_symbols = [
        {'symbol': '005930', 'name': '삼성전자'},
        {'symbol': '000660', 'name': 'SK하이닉스'},
        {'symbol': '035720', 'name': '카카오'},
        {'symbol': '035420', 'name': 'NAVER'},
        {'symbol': '005380', 'name': '현대차'},
        {'symbol': '005490', 'name': 'POSCO홀딩스'},
        {'symbol': '068270', 'name': '셀트리온'},
        # ... 기타 종목
    ]

    for item in all_symbols:
        symbol = item['symbol']
        name = item['name']

        # --- AI 및 통계 기반 필터링 로직 (가상) ---
        # 예시: 재무 데이터, 시장 데이터, 뉴스 등을 AI 모델에 입력하여 투자가치 판단
        # is_investable = AIModelHandler.predict_investability(symbol)
        # raw_data = kis_client.get_financial_data(symbol)
        
        # 임시 로직: 일단 모든 종목을 투자가치 있다고 가정
        is_investable = True
        raw_data = {'PER': 10.5, 'PBR': 1.2, 'ROE': 15.0} # 가상 데이터

        if is_investable:
            stock, created = AnalyzedStock.objects.update_or_create(
                symbol=symbol,
                defaults={
                    'stock_name': name,
                    'is_investable': True,
                    'analysis_date': date.today(),
                    'raw_analysis_data': raw_data
                }
            )
            if created:
                print(f"[{symbol}] {name}: 신규 관심 종목으로 추가.")
            else:
                print(f"[{symbol}] {name}: 기존 관심 종목 정보 업데이트.")

    print("--- 1차 분석: 종목 스크리닝 완료 ---")

# --- 2차 분석: 투자 기간 분류 ---
def classify_investment_horizon():
    """
    1차 분석을 통과한 종목들을 대상으로 AI 모델을 사용해 단기/중기/장기 투자 적합성을 분류합니다.
    """
    print("--- 2차 분석: 투자 기간 분류 시작 ---")
    investable_stocks = AnalyzedStock.objects.filter(is_investable=True)

    for stock in investable_stocks:
        # --- AI 및 통계 기반 기간 분류 로직 (가상) ---
        # 예시: 변동성, 성장성, 산업 사이클 등을 AI 모델이 분석하여 투자 기간 추천
        # horizon = AIModelHandler.predict_horizon(stock.symbol, stock.raw_analysis_data)
        
        # 임시 로직: 랜덤하게 기간 분류
        import random
        horizons = [AnalyzedStock.Horizon.SHORT, AnalyzedStock.Horizon.MID, AnalyzedStock.Horizon.LONG]
        horizon = random.choice(horizons)

        stock.investment_horizon = horizon
        stock.save()
        print(f"[{stock.symbol}] {stock.stock_name}: {stock.get_investment_horizon_display()} 투자로 분류.")

    print("--- 2차 분석: 투자 기간 분류 완료 ---")


# --- 3차 분석: 매매 전략 수립 및 포트폴리오 조정 ---
def establish_trading_strategies():
    """
    분류된 종목들을 바탕으로 구체적인 매매 전략(매수가, 목표가, 손절가)을 수립하고,
    기존 보유 종목(포트폴리오)의 상태를 점검 및 조정합니다.
    """
    print("--- 3차 분석: 매매 전략 수립 및 포트폴리오 조정 시작 ---")

    # 1. 기존 포트폴리오 점검 및 리밸런싱
    print("\n[단계 1/2] 기존 포트폴리오 점검 및 리밸런싱")
    all_open_positions = Portfolio.objects.filter(is_open=True)
    
    # kis_client = KISClient()
    for position in all_open_positions:
        # --- AI 및 통계 기반 목표가/손절가 재설정 로직 (가상) ---
        # current_price = kis_client.get_current_price(position.symbol)
        # new_target_price, new_stop_loss = AIModelHandler.rebalance_position(position, current_price)
        
        # 임시 로직: 현재가 기준 +/- 10%로 목표가, -5%로 손절가 재설정
        current_price = position.average_buy_price * Decimal(random.uniform(0.9, 1.2)) # 가상 현재가
        new_target_price = current_price * Decimal('1.10')
        new_stop_loss_price = current_price * Decimal('0.95')

        position.target_price = new_target_price
        position.stop_loss_price = new_stop_loss_price
        position.save()
        print(f"  - 보유 종목 [{position.symbol}] 점검: 목표가 {new_target_price:.2f}, 손절가 {new_stop_loss_price:.2f}로 업데이트.")


    # 2. 신규 투자 대상 분석 및 전략 수립
    print("\n[단계 2/2] 신규 투자 대상 분석 및 진입 전략 수립")
    analyzed_stocks = AnalyzedStock.objects.filter(is_investable=True).exclude(investment_horizon=AnalyzedStock.Horizon.NONE)
    
    for stock in analyzed_stocks:
        # --- AI 및 통계 기반 진입 전략 수립 로직 (가상) ---
        # current_price = kis_client.get_current_price(stock.symbol)
        # entry_signal = AIModelHandler.generate_entry_signal(stock, current_price) # 매수/보류/관망 등 신호
        
        # 임시 로직
        current_price = stock.last_price * Decimal(random.uniform(0.98, 1.02)) # 가상 현재가
        entry_signal = 'BUY' # 매수 신호 발생 가정

        if entry_signal == 'BUY':
            target_price = current_price * Decimal('1.15') # 목표가: 현재가 +15%
            stop_loss_price = current_price * Decimal('0.93') # 손절가: 현재가 -7%
            
            # TODO: 이 종목에 투자할 계좌와 자본금을 결정하는 로직 필요
            # 현재는 첫 번째 활성화된 계좌에 할당하는 것으로 가정
            active_accounts = TradingAccount.objects.filter(is_active=True)
            if not active_accounts.exists():
                continue
            
            account = active_accounts.first()
            
            # 이미 해당 계좌에 오픈된 포지션이 있는지 확인
            is_already_in_portfolio = Portfolio.objects.filter(account=account, symbol=stock.symbol, is_open=True).exists()

            if not is_already_in_portfolio:
                # 여기에 실제 매수 주문 로직을 넣는 대신, 포트폴리오에 '진입 대기' 상태로 등록
                # 실제 주문은 별도의 매매 실행 로직(run_all_active_strategies)에서 처리
                print(f"  - 신규 매수 신호 [{stock.symbol}]: 계좌 '{account.account_name}'에 진입 전략 설정 (목표가: {target_price:.2f}, 손절가: {stop_loss_price:.2f})")
                
                # Portfolio 모델에 반영 (실제 매수/보유는 아니지만, 관리 대상으로 등록)
                # 이 부분은 '모의' 포트폴리오로 관리하거나, 실제 주문 로직과 연계하는 방향으로 발전 가능
            else:
                print(f"  - 추가 매수 신호 [{stock.symbol}]: 이미 포트폴리오에 존재. (추가 매수 로직은 추후 구현)")

    print("--- 3차 분석: 모든 작업 완료 ---")