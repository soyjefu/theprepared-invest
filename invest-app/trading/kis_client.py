# invest-app/trading/kis_client.py

import requests
import json
from datetime import datetime, timedelta, time
from django.core.cache import cache
import pytz
import logging

logger = logging.getLogger(__name__)

class KISApiClient:
    # ... __init__ 부터 get_daily_price_history 까지는 이전과 동일 ...
    def __init__(self, app_key, app_secret, account_no, account_type='SIM'):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.account_type = account_type
        if self.account_type == 'REAL': self.base_url = "https://openapi.koreainvestment.com:9443"
        else: self.base_url = "https://openapivts.koreainvestment.com:29443"
        self.cache_key = f"kis_token_{self.app_key}"

    def _issue_token(self):
        path = "/oauth2/tokenP"
        url = f"{self.base_url}{path}"
        headers = {"content-type": "application/json"}
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        try:
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response.raise_for_status()
            result = response.json()
            token = f"Bearer {result['access_token']}"
            expires_in = int(result['expires_in'])
            cache.set(self.cache_key, token, timeout=expires_in - 300)
            print(f"✅ 새로운 토큰이 발급되어 캐시에 저장되었습니다. (유효시간: 약 {expires_in // 3600}시간)")
            return token
        except requests.exceptions.RequestException as e:
            print(f"🚨 토큰 발급 실패: {e}")
            response_text = response.text if 'response' in locals() else "응답 없음"
            print(f"응답 내용: {response_text}")
            return None

    def get_access_token(self):
        cached_token = cache.get(self.cache_key)
        if cached_token: return cached_token
        print("캐시에 토큰이 없거나 만료되어 새로 발급합니다.")
        return self._issue_token()

    def _send_request(self, method, path, params=None, body=None, tr_id=None):
        token = self.get_access_token()
        if not token: return None
        url = f"{self.base_url}{path}"
        headers = {"content-type": "application/json", "authorization": token, "appkey": self.app_key, "appsecret": self.app_secret}
        if tr_id: headers["tr_id"] = tr_id
        try:
            response = requests.get(url, headers=headers, params=params) if method.upper() == 'GET' else requests.post(url, headers=headers, data=json.dumps(body))
            return response.json()
        except requests.exceptions.RequestException as e: return None
        except json.JSONDecodeError: return {"rt_cd": "E", "msg1": "JSON 파싱 에러", "raw_response": response.text}
    
    def get_account_balance(self):
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.account_type == 'SIM' else "TTTC8434R"
        clean_account_no = self.account_no.replace('-', '')
        cano, acnt_prdt_cd = clean_account_no[:8], clean_account_no[8:]
        params = {"CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": "01", "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def get_current_price(self, symbol):
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = { "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol }
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def place_order(self, symbol, quantity, price, order_type='BUY', order_division="00"): # 수정: order_division 추가
        """주식을 주문합니다. (기본: 지정가)"""
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = ("VTTC0802U" if order_type.upper() == 'BUY' else "VTTC0801U") if self.account_type == 'SIM' else ("TTTC0802U" if order_type.upper() == 'BUY' else "TTTC0801U")
        clean_account_no = self.account_no.replace('-', '')
        cano, acnt_prdt_cd = clean_account_no[:8], clean_account_no[8:]
        body = {
            "CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "PDNO": symbol,
            "ORD_DVSN": order_division, # 수정: 파라미터로 받은 주문 구분 사용
            "ORD_QTY": str(quantity), "ORD_UNPR": str(price),
        }
        return self._send_request(method='POST', path=path, body=body, tr_id=tr_id)
        
    def get_daily_price_history(self, symbol, days=100):
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol, "FID_INPUT_DATE_1": start_date, "FID_INPUT_DATE_2": end_date, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1"}
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def is_market_open(self):
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "0001"}
        response = self._send_request(method='GET', path=path, params=params, tr_id=tr_id)
        if response and response.get('output', {}).get('bsop_yn') == 'Y': return True
        if self.account_type == 'SIM':
            tz, now = pytz.timezone('Asia/Seoul'), datetime.now(pytz.timezone('Asia/Seoul'))
            if 0 <= now.weekday() <= 4 and time(9, 0) <= now.time() <= time(15, 30):
                logger.warning("모의투자 환경: API는 장 마감으로 응답했으나, 시간상 장운영 시간이므로 '열림'으로 간주하여 테스트를 계속합니다.")
                return True
        return False

    # 수정: 거래량 상위 종목 조회 기능 추가
    def get_top_volume_stocks(self, market='KOSPI', top_n=20):
        """거래량 상위 종목 리스트를 반환합니다."""
        path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        
        market_code_map = {'KOSPI': '0', 'KOSDAQ': '1'}
        
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20171",
            "FID_INPUT_ISCD": market_code_map.get(market.upper(), '0'),
            "FID_DIV_CLS_CODE": "0", # 0: 제외안함
            "FID_BLNG_CLS_CODE": "0", # 0: 전체
            "FID_TRGT_CLS_CODE": "111111111", # 전체
            "FID_TRGT_EXLS_CLS_CODE": "000000", # 제외없음
            "FID_INPUT_PRICE_1": "",
            "FID_INPUT_PRICE_2": "",
            "FID_VOL_CNT": "",
            "FID_INPUT_DATE_1": ""
        }
        
        response = self._send_request(method='GET', path=path, params=params, tr_id=tr_id)
        
        if response and response.get('rt_cd') == '0':
            stocks = response.get('output', [])
            return [stock['mksc_shrn_iscd'] for stock in stocks[:top_n]]
        
        logger.error(f"[{market}] 거래량 상위 종목 조회 실패: {response}")
        return []