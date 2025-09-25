# invest-app/trading/analysis/market_scanner.py

import logging
import numpy as np
from django.core.cache import cache
from trading.models import AnalyzedStock, TradingAccount
from trading.kis_client import KISApiClient
from .stock_lists import get_market_tickers
from ..ai_analysis_service import analyze_stock, get_market_trend

logger = logging.getLogger(__name__)


def convert_numpy_types(obj):
    """
    Recursively converts numpy data types to native Python types for JSON serialization.

    The AI analysis service may return data using numpy types (e.g., np.int64,
    np.float64), which are not directly JSON serializable. This function
    traverses a nested data structure (dicts, lists) and converts these types.

    Args:
        obj: The object to convert (e.g., a dictionary or list).

    Returns:
        The object with all numpy types converted to native Python types.
    """
    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(i) for i in obj]
    elif isinstance(obj, (np.integer, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif obj is None:
        return None
    else:
        return obj


def screen_initial_stocks():
    """
    Performs the first stage of the stock screening process.

    This function iterates through a list of predefined blue-chip stocks and
    other market tickers, performs an AI analysis on each, and filters them
    based on the analysis results and other basic criteria (e.g., excluding
    ETFs, preferred stocks). The results are saved to the AnalyzedStock model.
    """
    logger.info("Starting Stage 1: Initial stock screening based on AI analysis.")

    first_account = TradingAccount.objects.filter(is_active=True).first()
    if not first_account:
        logger.error("Screening aborted: No active account available for API calls.")
        return

    client = KISApiClient(
        app_key=first_account.app_key,
        app_secret=first_account.app_secret,
        account_no=first_account.account_number,
        account_type=first_account.account_type
    )

    predefined_blue_chips = [
        "005930", "000660", "005380", "005490", "035420",
        "000270", "035720", "068270", "051910", "006400"
    ]

    try:
        market_tickers = get_market_tickers()
    except Exception as e:
        logger.error(f"Error fetching predefined stock list: {e}", exc_info=True)
        market_tickers = []

    target_symbols = list(set(predefined_blue_chips + market_tickers))

    if not target_symbols:
        logger.error("Screening aborted: No target symbols to analyze.")
        return

    market_trend = get_market_trend(client)
    logger.info(f"Today's market trend: {market_trend}")

    logger.info(f"Starting AI-based filtering for {len(target_symbols)} symbols.")

    # Before analysis, reset previous data
    AnalyzedStock.objects.all().update(is_investable=False, raw_analysis_data={})

    screened_count = 0
    total_symbols = len(target_symbols)
    for i, symbol in enumerate(target_symbols):
        progress = int(((i + 1) / total_symbols) * 95)
        status_text = f"AI Analyzing: {symbol} ({i + 1}/{total_symbols})"
        cache.set('screening_progress', {'status': status_text, 'progress': progress}, timeout=300)

        analysis_result = analyze_stock(symbol, client, market_trend)

        if not analysis_result:
            logger.warning(f"Excluding {symbol} from screening due to analysis failure.")
            continue

        price_info_response = client.get_current_price(symbol)
        if not (price_info_response and price_info_response.is_ok()):
            logger.warning(f"Skipping {symbol} due to failure in fetching current price.")
            continue
        price_info = price_info_response.get_body().get('output', {})
        stock_name = price_info.get('hts_kor_isnm', '')
        last_price = price_info.get('stck_prpr', '0')

        # Filter based on AI analysis horizon
        is_investable = analysis_result.horizon in ['SHORT', 'MID']
        reason = f"AI Analysis({analysis_result.horizon})"

        # Filter out ETFs, preferred stocks, etc.
        if not stock_name or stock_name.endswith('우') or any(keyword in stock_name for keyword in ['스팩', 'ETN', 'TIGER', 'KODEX']):
            if is_investable:
                reason += ", Basic Filter(Disqualified)"
                is_investable = False

        if is_investable:
            logger.info(f"[{symbol}] {stock_name}: Selected as investable candidate. ({reason})")
            screened_count += 1
        else:
            logger.info(f"[{symbol}] {stock_name}: Not qualified for investment. ({reason})")

        # Convert numpy types to native Python types before saving to JSONField
        cleaned_raw_data = convert_numpy_types(analysis_result.raw_data)

        AnalyzedStock.objects.update_or_create(
            symbol=symbol,
            defaults={
                'stock_name': stock_name,
                'is_investable': is_investable,
                'investment_horizon': analysis_result.horizon,
                'last_price': last_price,
                'raw_analysis_data': cleaned_raw_data
            }
        )

    logger.info(f"Initial screening complete. Saved {screened_count} investable candidates out of {len(target_symbols)} to the database.")