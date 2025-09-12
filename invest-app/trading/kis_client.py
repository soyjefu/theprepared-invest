# invest-app/trading/kis_client.py
# ... 상단 코드는 이전과 동일 ...
import requests
import json
from datetime import datetime, timedelta, time
import time
import os
from django.core.cache import cache
import pytz
import logging
import websockets
from collections import namedtuple
from base64 import b64decode
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import asyncio

logger = logging.getLogger(__name__)

class KISAPIResponse:
    def __init__(self, response):
        self._response = response
        self._json_data = None
        try:
            self._json_data = response.json()
        except json.JSONDecodeError:
            self._json_data = None

    def is_ok(self):
        return self._response.status_code == 200 and self._json_data and self._json_data.get('rt_cd') == '0'

    def get_error_code(self):
        if self._json_data:
            return self._json_data.get('msg_cd')
        return None

    def get_error_message(self):
        if self._json_data:
            return self._json_data.get('msg1')
        return self._response.text

    def get_body(self):
        return self._json_data

    @property
    def text(self):
        return self._response.text


class KISApiClient:
    def __init__(self, app_key, app_secret, account_no, account_type='SIM'):
        self.app_key = app_key
        self.app_secret = app_secret
        self.account_no = account_no
        self.account_type = account_type
        if self.account_type == 'REAL':
            self.base_url = "https://openapi.koreainvestment.com:9443"
        else:
            self.base_url = "https://openapivts.koreainvestment.com:29443"
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
        if cached_token:
            return cached_token
        print("캐시에 토큰이 없거나 만료되어 새로 발급합니다.")
        return self._issue_token()

    def _send_request(self, method, path, params=None, body=None, tr_id=None, retries=3, delay=5):
        token = self.get_access_token()
        if not token:
            return None
        url = f"{self.base_url}{path}"
        headers = {
            "content-type": "application/json",
            "authorization": token,
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        if tr_id:
            headers["tr_id"] = tr_id

        for i in range(retries):
            try:
                if method.upper() == 'GET':
                    response = requests.get(url, headers=headers, params=params)
                else:
                    response = requests.post(url, headers=headers, data=json.dumps(body))

                response.raise_for_status()
                return KISAPIResponse(response)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed: {e}. Retrying ({i+1}/{retries}) in {delay} seconds...")
                time.sleep(delay)

        logger.error(f"Request failed after {retries} retries.")
        return None

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

    def place_order(self, symbol, quantity, price, order_type='BUY', order_division="00"):
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = ("VTTC0802U" if order_type.upper() == 'BUY' else "VTTC0801U") if self.account_type == 'SIM' else ("TTTC0802U" if order_type.upper() == 'BUY' else "TTTC0801U")
        clean_account_no = self.account_no.replace('-', '')
        cano, acnt_prdt_cd = clean_account_no[:8], clean_account_no[8:]
        body = {"CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "PDNO": symbol, "ORD_DVSN": order_division, "ORD_QTY": str(quantity), "ORD_UNPR": str(price)}
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
        if response and response.is_ok():
            body = response.get_body()
            if body.get('output', {}).get('bsop_yn') == 'Y':
                return True
        if self.account_type == 'SIM':
            tz = pytz.timezone('Asia/Seoul')
            now = datetime.now(tz)
            if 0 <= now.weekday() <= 4 and time(9, 0) <= now.time() <= time(15, 30):
                logger.warning("모의투자 환경: API는 장 마감으로 응답했으나, 시간상 장운영 시간이므로 '열림'으로 간주하여 테스트를 계속합니다.")
                return True
        return False

    def get_top_volume_stocks(self, market='KOSPI', top_n=20):
        path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        market_code_map = {'KOSPI': '0', 'KOSDAQ': '1'}
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": market_code_map.get(market.upper(), '0'), "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "000000", "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""}
        response = self._send_request(method='GET', path=path, params=params, tr_id=tr_id)
        if response and response.is_ok():
            stocks = response.get_body().get('output', [])
            return [stock['mksc_shrn_iscd'] for stock in stocks[:top_n]]
        logger.error(f"[{market}] 거래량 상위 종목 조회 실패: {response.get_error_message() if response else 'No response'}")
        return []
    
    def get_all_stock_codes(self, mst_file_path=None):
        """
        Reads KOSPI and KOSDAQ stock codes from local .mst files.

        These files are expected to be downloaded by the official KIS application
        and located in a specific directory. The default path for Windows is
        C:\\KIS\\ubin\\mst.

        Args:
            mst_file_path (str, optional): The directory path where the .mst files are located.
                                           If not provided, it defaults to a common path
                                           based on the operating system.

        Returns:
            dict: A dictionary mapping stock codes to stock names.
        """
        if mst_file_path is None:
            if os.name == 'nt':
                mst_file_path = 'C:\\KIS\\ubin\\mst'
            else:
                # Provide a default path for non-Windows systems, which the user should configure.
                mst_file_path = '/tmp/kis_mst'
                logger.warning(f"No mst_file_path provided. Defaulting to {mst_file_path}. "
                               f"Please ensure the .mst files are located in this directory or "
                               f"provide the correct path.")

        all_stocks = {}
        for market_code in ["kospi", "kosdaq"]:
            file_name = f"{market_code}_code.mst"
            full_path = os.path.join(mst_file_path, file_name)

            logger.info(f"Reading stock codes from {full_path}...")
            try:
                with open(full_path, 'rb') as f:
                    file_content = f.read()
                    stocks = self._parse_mst_file(file_content)
                    all_stocks.update(stocks)
            except FileNotFoundError:
                logger.error(f"File not found: {full_path}. Please make sure the KIS application "
                               f"has downloaded the stock code files.")
            except Exception as e:
                logger.error(f"Failed to read or parse {full_path}: {e}")

        return all_stocks

    def _parse_mst_file(self, file_content):
        """
        Parses the content of a .mst file to extract stock codes and names.

        NOTE: The format of the .mst file is not publicly documented.
              This implementation is a placeholder and needs to be adapted
              to the actual file format. The user should inspect the .mst
              file and provide the correct parsing logic.

        This placeholder assumes a simple text file with each line containing
        a stock code and name, separated by a comma.
        Example: "005930,Samsung Electronics"
        """
        all_stocks = {}
        if not file_content:
            return all_stocks

        try:
            # The encoding is likely 'cp949' for Korean financial data.
            decoded_content = file_content.decode('cp949')
            for line in decoded_content.splitlines():
                line = line.strip()
                if not line:
                    continue

                # This is a placeholder parsing logic. The actual format might be different.
                # For example, it could be a fixed-width format.
                # The user needs to inspect the file and adjust this logic.
                parts = line.split(',')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    # A simple check to filter out header or invalid lines
                    if code.isdigit() and len(code) == 6:
                        all_stocks[code] = name

            if not all_stocks:
                logger.warning("Parsing .mst file did not yield any stock codes. "
                               "The file format might be different from the placeholder implementation.")

        except Exception as e:
            logger.error(f"Failed to parse .mst file content: {e}")

        return all_stocks

    def get_ws_approval_key(self):
        """Get WebSocket approval key."""
        path = "/oauth2/Approval"
        url = f"{self.base_url}{path}"
        headers = {"content-type": "application/json"}
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "secretkey": self.app_secret}

        response = requests.post(url, headers=headers, data=json.dumps(body))

        if response.status_code == 200:
            return response.json().get('approval_key')
        else:
            logger.error(f"Failed to get WebSocket approval key: {response.text}")
            return None

class KISWebSocket:
    def __init__(self, client, on_message_callback):
        self._client = client
        self._on_message_callback = on_message_callback
        self._ws = None

    async def connect(self):
        approval_key = self._client.get_ws_approval_key()
        if not approval_key:
            return

        ws_url = "ws://ops.koreainvestment.com:21000" if self._client.account_type == 'REAL' else "ws://ops.koreainvestment.com:31000"

        self._ws = await websockets.connect(ws_url)
        logger.info("WebSocket connected.")

    async def subscribe(self, tr_id, tr_key):
        if not self._ws:
            logger.error("WebSocket not connected.")
            return

        message = {
            "header": {
                "approval_key": self._client.get_ws_approval_key(),
                "custtype": "P",
                "tr_type": "1",
                "content-type": "utf-8"
            },
            "body": {
                "input": {
                    "tr_id": tr_id,
                    "tr_key": tr_key
                }
            }
        }
        await self._ws.send(json.dumps(message))
        logger.info(f"Subscribed to {tr_id} with key {tr_key}")

    async def receive_messages(self):
        if not self._ws:
            logger.error("WebSocket not connected.")
            return

        async for message in self._ws:
            self._handle_message(message)

    def _handle_message(self, message):
        if message[0] in ['0', '1']:  # Real-time data
            parts = message.split('|')
            tr_id = parts[1]
            data_str = parts[3]

            # Decryption logic for encrypted data
            if 'encrypted' in message: # This is a placeholder for the actual encryption check
                # The official script uses AES decryption. This needs to be implemented here.
                # For now, we just log the encrypted data.
                logger.warning(f"Received encrypted data for {tr_id}. Decryption not yet implemented.")
                logger.info(data_str)
            else:
                logger.info(f"Received data for {tr_id}: {data_str}")

            if self._on_message_callback:
                self._on_message_callback(tr_id, data_str)
        else: # System messages
            try:
                data = json.loads(message)
                if data.get('header', {}).get('tr_id') == 'PINGPONG':
                    logger.info("Received PINGPONG")
                    asyncio.create_task(self._ws.pong(message))
                else:
                    logger.info(f"Received system message: {message}")
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON message: {message}")