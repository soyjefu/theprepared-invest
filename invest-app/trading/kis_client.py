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
from decimal import Decimal
from trading.models import TradeLog, TradingAccount

logger = logging.getLogger(__name__)

class KISAPIResponse:
    """
    A wrapper class for responses from the KIS (Korea Investment & Securities) API.

    This class standardizes the way API responses are handled, providing
    methods to check for success, and access error details or the response body.

    Attributes:
        _response (requests.Response): The original HTTP response object.
        _json_data (dict | None): The JSON-decoded response body.
    """
    def __init__(self, response):
        """
        Initializes the KISAPIResponse object.

        Args:
            response (requests.Response): The HTTP response from the requests library.
        """
        self._response = response
        self._json_data = None
        try:
            self._json_data = response.json()
        except json.JSONDecodeError:
            self._json_data = None

    def is_ok(self):
        """
        Checks if the API call was successful.

        A successful call has an HTTP status of 200 and the 'rt_cd' in the
        JSON response body is '0'.

        Returns:
            bool: True if the API call was successful, False otherwise.
        """
        return self._response.status_code == 200 and self._json_data and self._json_data.get('rt_cd') == '0'

    def get_error_code(self):
        """
        Retrieves the error code from the API response body.

        Returns:
            str | None: The error code (msg_cd) if it exists, otherwise None.
        """
        if self._json_data:
            return self._json_data.get('msg_cd')
        return None

    def get_error_message(self):
        """
        Retrieves the error message from the API response body.

        If the body does not contain a message, it returns the full response text.

        Returns:
            str: The error message (msg1) or the full response text.
        """
        if self._json_data:
            return self._json_data.get('msg1')
        return self._response.text

    def get_body(self):
        """
        Returns the full JSON response body.

        Returns:
            dict | None: The parsed JSON data if available, otherwise None.
        """
        return self._json_data

    @property
    def text(self):
        """
        Returns the raw text of the response.

        Returns:
            str: The raw HTTP response text.
        """
        return self._response.text


class KISApiClient:
    """
    A client for interacting with the KIS (Korea Investment & Securities) API.

    This class handles authentication, request signing, and provides methods
    for various API endpoints such as fetching account balances, placing orders,
    and getting market data.

    Attributes:
        app_key (str): The application key for API access.
        app_secret (str): The application secret for API access.
        account_no (str): The user's trading account number.
        account_type (str): 'REAL' for a real trading account or 'SIM' for a
                            simulation account.
        base_url (str): The base URL for the KIS API, determined by account_type.
        cache_key (str): The key used for caching the access token.
    """
    def __init__(self, app_key, app_secret, account_no, account_type='SIM'):
        """
        Initializes the KISApiClient.

        Args:
            app_key (str): The KIS API application key.
            app_secret (str): The KIS API application secret.
            account_no (str): The trading account number.
            account_type (str, optional): The type of account ('REAL' or 'SIM').
                                          Defaults to 'SIM'.
        """
        logger.info(f"KISApiClient instantiated for account {account_no} (type: {account_type})")
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
        """
        Issues a new access token from the KIS API and caches it.

        This is a private method called by get_access_token when a valid
        token is not found in the cache.

        Returns:
            str | None: The new access token if successful, otherwise None.
        """
        path = "/oauth2/tokenP"
        url = f"{self.base_url}{path}"
        headers = {"content-type": "application/json"}
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}
        try:
            response = requests.post(url, headers=headers, data=json.dumps(body))
            response.raise_for_status()
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Failed to issue token (JSONDecodeError): {e}")
                logger.error(f"Response content (status {response.status_code}): {response.text}")
                return None

            token = f"Bearer {result['access_token']}"
            expires_in = int(result.get('expires_in', 86400))
            cache.set(self.cache_key, token, timeout=expires_in - 300)
            logger.info(f"New token has been issued and cached. (Expires in: ~{expires_in // 3600} hours)")
            return token
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to issue token (RequestException): {e}")
            response_text = response.text if 'response' in locals() else "No response"
            logger.error(f"Response content: {response_text}")
            return None

    def get_access_token(self):
        """
        Retrieves a valid access token, either from the cache or by issuing a new one.

        Returns:
            str | None: A valid access token if available, otherwise None.
        """
        cached_token = cache.get(self.cache_key)
        if cached_token:
            return cached_token
        logger.info("Token not in cache or expired, issuing a new one.")
        return self._issue_token()

    def _send_request(self, method, path, params=None, body=None, tr_id=None, retries=3, delay=5):
        """
        Sends a request to the KIS API with authentication and retries.

        Args:
            method (str): The HTTP method ('GET', 'POST', etc.).
            path (str): The API endpoint path.
            params (dict, optional): URL parameters for 'GET' requests.
            body (dict, optional): The request body for 'POST' requests.
            tr_id (str, optional): The transaction ID for the API call.
            retries (int, optional): The number of times to retry on failure.
            delay (int, optional): The delay in seconds between retries.

        Returns:
            KISAPIResponse | None: A response object if the request was sent,
                                  otherwise None.
        """
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
                api_response = KISAPIResponse(response)
                if not api_response.is_ok():
                    logger.warning(f"KIS API call was not successful (rt_cd != '0'). "
                                   f"URL: {url}, "
                                   f"TR_ID: {headers.get('tr_id')}, "
                                   f"Response: {api_response.text}")
                return api_response
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed: {e}. Retrying ({i+1}/{retries}) in {delay} seconds...")
                time.sleep(delay)

        logger.error(f"Request failed after {retries} retries.")
        return None

    def get_account_balance(self):
        """
        Fetches the current balance and holdings for the account.

        Returns:
            KISAPIResponse | None: The API response object.
        """
        path = "/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if self.account_type == 'SIM' else "TTTC8434R"
        # 모의투자에서는 "01" (대출일자별) 조회가 불안정하여 "02" (종목별)로 변경
        inqr_dvsn = "02" if self.account_type == 'SIM' else "01"
        clean_account_no = self.account_no.replace('-', '')
        cano, acnt_prdt_cd = clean_account_no[:8], clean_account_no[8:]
        params = {"CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "AFHR_FLPR_YN": "N", "OFL_YN": "", "INQR_DVSN": inqr_dvsn, "UNPR_DVSN": "01", "FUND_STTL_ICLD_YN": "N", "FNCG_AMT_AUTO_RDPT_YN": "N", "PRCS_DVSN": "00", "CTX_AREA_FK100": "", "CTX_AREA_NK100": ""}
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def get_current_price(self, symbol):
        """
        Fetches the current market price for a given stock symbol.

        Args:
            symbol (str): The stock symbol (ticker).

        Returns:
            KISAPIResponse | None: The API response object.
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = { "FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol }
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def place_order(self, account: TradingAccount, symbol: str, quantity: int, price: int, order_type: str, order_division="00", fee_rate=0.00015):
        """
        Places a buy or sell order after performing server-side validation.

        Args:
            account: The TradingAccount instance for this order.
            symbol: The stock symbol (ticker).
            quantity: The number of shares to trade.
            price: The price per share.
            order_type: 'BUY' or 'SELL'.
            order_division: The order type code (e.g., "00" for limit order).
            fee_rate (float): The transaction fee rate.

        Returns:
            A dictionary with the API response or an error message.
        """
        logger.info(f"Order received for Account ID {account.id}: {order_type} {quantity} of {symbol} @ {price}")

        # 1. Check for duplicate pending orders
        if TradeLog.objects.filter(account=account, symbol=symbol, trade_type=order_type.upper(), status='PENDING').exists():
            msg = f"Duplicate order prevented for {symbol}. An order is already pending."
            logger.warning(msg)
            return {'rt_cd': '99', 'msg1': msg, 'is_validation_error': True}

        # 2. Check balance and holdings
        balance_res = self.get_account_balance()
        if not balance_res or not balance_res.is_ok():
            msg = "Failed to verify account balance before placing order."
            logger.error(f"{msg} Response: {balance_res.text if balance_res else 'No Response'}")
            return {'rt_cd': '99', 'msg1': msg, 'is_validation_error': True}

        balance_body = balance_res.get_body()

        if order_type.upper() == 'BUY':
            cash_available = Decimal(balance_body.get('output2', [{}])[0].get('dnca_tot_amt', '0'))
            order_amount = Decimal(quantity) * Decimal(price)
            order_total_with_fee = order_amount * (Decimal('1') + Decimal(str(fee_rate)))

            if cash_available < order_total_with_fee:
                msg = f"Insufficient funds to place buy order for {symbol}. Required (incl. fee): {order_total_with_fee:.2f}, Available: {cash_available}"
                logger.warning(msg)
                return {'rt_cd': '99', 'msg1': msg, 'is_validation_error': True}

        elif order_type.upper() == 'SELL':
            holdings = balance_body.get('output1', [])
            stock_holding = next((item for item in holdings if item['pdno'] == symbol), None)
            if not stock_holding or int(stock_holding.get('hldg_qty', 0)) < quantity:
                held_qty = stock_holding.get('hldg_qty', 0) if stock_holding else 0
                msg = f"Insufficient holdings to place sell order for {symbol}. Required: {quantity}, Held: {held_qty}"
                logger.warning(msg)
                return {'rt_cd': '99', 'msg1': msg, 'is_validation_error': True}

        # 3. Create a pending TradeLog BEFORE sending the order
        pending_log = TradeLog.objects.create(
            account=account,
            symbol=symbol,
            order_id='N/A_PENDING', # Placeholder ID
            trade_type=order_type.upper(),
            quantity=quantity,
            price=price,
            status='PENDING',
            log_message=f"Order validation passed. Sending to broker."
        )

        # 4. Proceed with placing the order via API
        path = "/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = ("VTTC0802U" if order_type.upper() == 'BUY' else "VTTC0801U") if self.account_type == 'SIM' else ("TTTC0802U" if order_type.upper() == 'BUY' else "TTTC0801U")
        clean_account_no = self.account_no.replace('-', '')
        cano, acnt_prdt_cd = clean_account_no[:8], clean_account_no[8:]
        body = {"CANO": cano, "ACNT_PRDT_CD": acnt_prdt_cd, "PDNO": symbol, "ORD_DVSN": order_division, "ORD_QTY": str(quantity), "ORD_UNPR": str(price)}

        api_response = self._send_request(method='POST', path=path, body=body, tr_id=tr_id)

        # 5. Update the log based on the API response
        if api_response and api_response.is_ok():
            response_body = api_response.get_body()
            order_id = response_body.get('output', {}).get('ODNO', 'N/A_SUCCESS')
            pending_log.order_id = order_id
            pending_log.log_message = "Order successfully sent to broker. Awaiting execution confirmation."
            # The status remains PENDING until the websocket confirms execution.
            pending_log.save()
            logger.info(f"Order for {symbol} sent successfully. Order ID: {order_id}")
        else:
            error_msg = api_response.get_error_message() if api_response else "No response from API."
            pending_log.status = 'FAILED'
            pending_log.log_message = f"Broker API rejected the order. Reason: {error_msg}"
            pending_log.save()
            logger.error(f"Failed to place order for {symbol}. Reason: {error_msg}")

        return api_response.get_body() if api_response else {'rt_cd': '99', 'msg1': 'API request failed.'}

    def get_daily_price_history(self, symbol, days=100):
        """
        Fetches the daily price chart history for a stock.

        Args:
            symbol (str): The stock symbol (ticker).
            days (int, optional): The number of days of history to retrieve.
                                  Defaults to 100.

        Returns:
            KISAPIResponse | None: The API response object containing historical data.
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
        tr_id = "FHKST03010100"
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol, "FID_INPUT_DATE_1": start_date, "FID_INPUT_DATE_2": end_date, "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "1"}
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def get_financial_info(self, symbol, year_gb='0'):
        """
        Fetches financial ratio data for a given stock symbol.
        (국내주식 재무비율)

        Args:
            symbol (str): The stock symbol (ticker).
            year_gb (str): '0' for yearly data, '1' for quarterly data.

        Returns:
            KISAPIResponse | None: The API response object.
        """
        path = "/uapi/domestic-stock/v1/finance/financial-ratio"
        tr_id = "FHKST66430300"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": symbol,
            "fid_div_cls_code": year_gb
        }
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def get_stock_info(self, symbol):
        """
        Fetches basic information for a given stock symbol, including industry.
        (주식기본정보조회)

        Args:
            symbol (str): The stock symbol (ticker).

        Returns:
            KISAPIResponse | None: The API response object.
        """
        path = "/uapi/domestic-stock/v1/quotations/search-stock-info"
        tr_id = "CTPF1002R"
        params = {
            "PRDT_TYPE_CD": "300",  # 300 for stocks
            "PDNO": symbol
        }
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def get_intraday_investor_summary(self, market_code='0000', amount_gb='1', buy_sell_gb='0', investor_gb='2'):
        """
        Fetches intraday provisional net buy/sell data for investors.
        (국내기관/외국인 매매종목 가집계)

        Args:
            market_code (str): Market code. '0000' for all, '0001' for KOSPI, '1001' for KOSDAQ.
            amount_gb (str): '0' for quantity, '1' for amount.
            buy_sell_gb (str): '0' for net buy, '1' for net sell.
            investor_gb (str): '0' for all, '1' for foreigner, '2' for institution, '3' for others.

        Returns:
            KISAPIResponse | None: The API response object.
        """
        path = "/uapi/domestic-stock/v1/quotations/foreign-institution-total"
        tr_id = "FHPTJ04400000"
        params = {
            "FID_COND_MRKT_DIV_CODE": "V",
            "FID_COND_SCR_DIV_CODE": "16449",
            "FID_INPUT_ISCD": market_code,
            "FID_DIV_CLS_CODE": amount_gb,
            "FID_RANK_SORT_CLS_CODE": buy_sell_gb,
            "FID_ETC_CLS_CODE": investor_gb
        }
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def get_index_price_history(self, symbol, days=100):
        """
        Fetches the daily price chart history for a given index.
        (국내주식업종기간별시세)

        Args:
            symbol (str): The index symbol (e.g., '0001' for KOSPI).
            days (int, optional): The number of days of history to retrieve.

        Returns:
            KISAPIResponse | None: The API response object containing historical data.
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
        tr_id = "FHKUP03500100"
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        params = {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": symbol, "FID_INPUT_DATE_1": start_date, "FID_INPUT_DATE_2": end_date, "FID_PERIOD_DIV_CODE": "D"}
        return self._send_request(method='GET', path=path, params=params, tr_id=tr_id)

    def is_market_open(self):
        """
        Checks if the Korean stock market is currently open.

        For simulation accounts, it provides a fallback check based on the
        current time if the API reports the market as closed during typical
        trading hours.

        Returns:
            bool: True if the market is open, False otherwise.
        """
        path = "/uapi/domestic-stock/v1/quotations/inquire-price"
        tr_id = "FHKST01010100"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "0001"} # Using a dummy code
        response = self._send_request(method='GET', path=path, params=params, tr_id=tr_id)
        if response and response.is_ok():
            body = response.get_body()
            if body.get('output', {}).get('bsop_yn') == 'Y':
                return True

        # Fallback for simulation environment during market hours
        if self.account_type == 'SIM':
            tz = pytz.timezone('Asia/Seoul')
            now = datetime.now(tz)
            if 0 <= now.weekday() <= 4 and time(9, 0) <= now.time() <= time(15, 30):
                logger.warning("Simulation Env: API reports market closed, but "
                               "continuing as if open due to time of day.")
                return True
        return False

    def get_top_volume_stocks(self, market='KOSPI', top_n=20):
        """
        Fetches a list of top stocks by trading volume for a given market.

        Args:
            market (str, optional): The market to query ('KOSPI' or 'KOSDAQ').
                                    Defaults to 'KOSPI'.
            top_n (int, optional): The number of top stocks to return.
                                   Defaults to 20.

        Returns:
            list[str]: A list of stock symbols.
        """
        path = "/uapi/domestic-stock/v1/quotations/volume-rank"
        tr_id = "FHPST01710000"
        market_code_map = {'KOSPI': '0', 'KOSDAQ': '1'}
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_COND_SCR_DIV_CODE": "20171", "FID_INPUT_ISCD": market_code_map.get(market.upper(), '0'), "FID_DIV_CLS_CODE": "0", "FID_BLNG_CLS_CODE": "0", "FID_TRGT_CLS_CODE": "111111111", "FID_TRGT_EXLS_CLS_CODE": "000000", "FID_INPUT_PRICE_1": "", "FID_INPUT_PRICE_2": "", "FID_VOL_CNT": "", "FID_INPUT_DATE_1": ""}
        response = self._send_request(method='GET', path=path, params=params, tr_id=tr_id)
        if response and response.is_ok():
            stocks = response.get_body().get('output', [])
            return [stock['mksc_shrn_iscd'] for stock in stocks[:top_n]]
        logger.error(f"Failed to get top volume stocks for {market}: "
                       f"{response.get_error_message() if response else 'No response'}")
        return []
    
    def get_all_stock_codes(self, mst_file_path=None):
        """
        Reads KOSPI and KOSDAQ stock codes from local .mst files.

        These files are proprietary to KIS and are expected to be downloaded
        by their official desktop application.

        Args:
            mst_file_path (str, optional): The directory path containing the .mst files.
                                           If None, defaults to a common path based on OS.

        Returns:
            dict: A dictionary mapping stock codes (str) to stock names (str).
        """
        if mst_file_path is None:
            if os.name == 'nt':
                mst_file_path = 'C:\\KIS\\ubin\\mst'
            else:
                mst_file_path = '/tmp/kis_mst'
                logger.warning(f"No mst_file_path provided. Defaulting to {mst_file_path}. "
                               f"Ensure .mst files are present or provide the correct path.")

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
                logger.error(f"File not found: {full_path}. Ensure the KIS desktop "
                               f"application has downloaded the necessary files.")
            except Exception as e:
                logger.error(f"Failed to read or parse {full_path}: {e}")

        return all_stocks

    def _parse_mst_file(self, file_content):
        """
        Parses the binary content of a .mst file to extract stock codes and names.

        NOTE: The .mst file format is not publicly documented. This implementation
              is a placeholder and likely needs to be adapted to the actual
              file format, which might be fixed-width or have a different encoding.

        Args:
            file_content (bytes): The raw byte content of the .mst file.

        Returns:
            dict: A dictionary mapping stock codes to stock names.
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

                # Placeholder parsing logic: Assumes comma-separated values.
                # This needs to be adjusted based on the actual file format.
                parts = line.split(',')
                if len(parts) >= 2:
                    code = parts[0]
                    name = parts[1]
                    if code.isdigit() and len(code) == 6:
                        all_stocks[code] = name

            if not all_stocks:
                logger.warning("Parsing .mst file yielded no stock codes. "
                               "The file format may differ from the placeholder implementation.")

        except Exception as e:
            logger.error(f"Failed to parse .mst file content: {e}")

        return all_stocks

    def get_ws_approval_key(self):
        """
        Gets an approval key required for establishing a WebSocket connection.

        Returns:
            str | None: The approval key if successful, otherwise None.
        """
        path = "/oauth2/Approval"
        url = f"{self.base_url}{path}"
        headers = {"content-type": "application/json"}
        body = {"grant_type": "client_credentials", "appkey": self.app_key, "appsecret": self.app_secret}

        response = requests.post(url, headers=headers, data=json.dumps(body))

        if response.status_code == 200:
            return response.json().get('approval_key')
        else:
            logger.error(f"Failed to get WebSocket approval key: {response.text}")
            return None

class KISWebSocket:
    """
    A WebSocket client for receiving real-time data from the KIS API.

    This class is a placeholder and requires a more complete implementation
    for production use, including robust error handling, reconnection logic,
    and message decryption.

    Attributes:
        _client (KISApiClient): The API client instance for getting credentials.
        _on_message_callback (callable): A callback function to handle incoming messages.
        _ws (websockets.WebSocketClientProtocol): The WebSocket connection object.
    """
    def __init__(self, client, on_message_callback):
        """
        Initializes the KISWebSocket client.

        Args:
            client (KISApiClient): An instance of the KISApiClient.
            on_message_callback (callable): A function to be called with (tr_id, data).
        """
        self._client = client
        self._on_message_callback = on_message_callback
        self._ws = None

    async def connect(self):
        """Establishes a connection to the KIS WebSocket server."""
        approval_key = self._client.get_ws_approval_key()
        if not approval_key:
            return

        ws_url = "ws://ops.koreainvestment.com:21000" if self._client.account_type == 'REAL' else "ws://ops.koreainvestment.com:31000"

        self._ws = await websockets.connect(ws_url)
        logger.info("WebSocket connected.")

    async def subscribe(self, tr_id, tr_key):
        """
        Subscribes to a real-time data feed.

        Args:
            tr_id (str): The transaction ID of the data feed (e.g., 'H0STCNI0' for executions).
            tr_key (str): The key for the subscription (e.g., a stock symbol or account ID).
        """
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
        """Listens for incoming messages and passes them to the handler."""
        if not self._ws:
            logger.error("WebSocket not connected.")
            return

        async for message in self._ws:
            self._handle_message(message)

    def _handle_message(self, message):
        """
        Handles an incoming WebSocket message.

        This method parses the message, identifies its type (data or system message),
        and calls the message callback. It includes placeholder logic for
        decryption and PING/PONG handling.

        Args:
            message (str): The raw message received from the WebSocket.
        """
        if message[0] in ['0', '1']:  # Real-time data
            parts = message.split('|')
            tr_id = parts[1]
            data_str = parts[3]

            # Placeholder for decryption logic
            if 'encrypted' in message: # This check needs to be more specific
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
                    logger.info("Received PINGPONG, sending PONG.")
                    asyncio.create_task(self._ws.pong(message))
                else:
                    logger.info(f"Received system message: {message}")
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON system message: {message}")