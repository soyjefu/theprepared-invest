import logging
import pandas as pd
import pandas_ta as ta
from prophet import Prophet
from dataclasses import dataclass
from typing import Dict, Any

from .kis_client import KISApiClient
from .models import TradingAccount

logger = logging.getLogger(__name__)

@dataclass
class StockAnalysisResult:
    """
    A data class to hold the results of a stock analysis.

    Attributes:
        symbol (str): The stock symbol (ticker).
        horizon (str): The recommended investment horizon (e.g., 'SHORT', 'MID', 'LONG', 'NONE').
        stop_loss_price (float): The calculated price at which to sell to limit losses.
        target_price (float): The calculated price at which to sell for a profit.
        raw_data (Dict[str, Any]): A dictionary containing the raw technical indicator
                                   values and other data used in the analysis.
    """
    symbol: str
    horizon: str
    stop_loss_price: float
    target_price: float
    raw_data: Dict[str, Any]

from decimal import Decimal

@dataclass
class DetailedStrategyResult:
    """
    A data class for a detailed, actionable trading strategy.

    Attributes:
        buy_quantity (int): The suggested number of shares to purchase.
        target_price (float): The calculated price at which to sell for a profit.
        stop_loss_price (float): The calculated price at which to sell to limit losses.
        raw_data (Dict[str, Any]): A dictionary containing raw data used for the calculation.
    """
    buy_quantity: int
    target_price: float
    stop_loss_price: float
    raw_data: Dict[str, Any]

def get_detailed_strategy(user, symbol: str, horizon: str) -> DetailedStrategyResult:
    """
    Generates a detailed trading strategy for a stock and investment horizon.

    This function calculates a suggested buy quantity based on the user's
    available cash and provides specific stop-loss and target prices.

    Args:
        user (User): The Django user instance requesting the strategy.
        symbol (str): The stock symbol to analyze.
        horizon (str): The desired investment horizon ('SHORT', 'MID', 'LONG').

    Returns:
        DetailedStrategyResult | None: A data class with the strategy details,
                                      or None if the analysis fails.
    """
    logger.info(f"AI Service: Starting detailed strategy analysis for symbol {symbol}, horizon {horizon}...")

    # 1. Get user's active account and initialize API client
    try:
        account = TradingAccount.objects.filter(user=user, is_active=True).first()
        if not account:
            raise ValueError("User does not have an active trading account.")

        client = KISApiClient(
            app_key=account.app_key,
            app_secret=account.app_secret,
            account_no=account.account_number,
            account_type=account.account_type
        )
    except Exception as e:
        logger.error(f"Failed to initialize client for user {user}: {e}", exc_info=True)
        return None

    # 2. Fetch and prepare data
    try:
        history_response = client.get_daily_price_history(symbol, days=730)
        if not history_response or not history_response.is_ok():
            logger.error(f"Failed to fetch historical data for {symbol}: {history_response.get_error_message()}")
            return None

        price_history = history_response.get_body().get('output2')
        if not price_history:
            logger.warning(f"No historical data in response for {symbol}.")
            return None

        df = pd.DataFrame(price_history)
        df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d')
        numeric_cols = ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'acml_tr_pbmn']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.set_index('stck_bsop_date').sort_index()
        df.rename(columns={'stck_oprc': 'open', 'stck_hgpr': 'high', 'stck_lwpr': 'low', 'stck_clpr': 'close', 'acml_vol': 'volume'}, inplace=True)
        df.dropna(inplace=True)

    except Exception as e:
        logger.error(f"Error processing data for {symbol}: {e}", exc_info=True)
        return None

    if df.empty:
        logger.warning(f"No historical data available for {symbol} after processing.")
        return None

    # 3. Technical Analysis
    try:
        df.ta.atr(length=14, append=True)
        latest_indicators = df.iloc[-1]
        latest_close = latest_indicators['close']
        latest_atr = latest_indicators.get('ATRr_14')
        if not latest_atr or latest_atr == 0:
            latest_atr = latest_close * 0.05 # Fallback ATR
    except Exception as e:
        logger.error(f"Failed to calculate technical indicators for {symbol}: {e}", exc_info=True)
        return None

    # 4. Horizon-adjusted Risk Levels
    horizon_factors = {
        'SHORT': {'stop_loss': 1.5, 'target': 3.0},
        'MID': {'stop_loss': 2.0, 'target': 4.0},
        'LONG': {'stop_loss': 2.5, 'target': 5.0}
    }
    factors = horizon_factors.get(horizon, horizon_factors['MID']) # Default to MID
    stop_loss_price = latest_close - (factors['stop_loss'] * latest_atr)
    target_price = latest_close + (factors['target'] * latest_atr)

    # 5. Calculate Buy Quantity based on account balance
    buy_quantity = 0
    try:
        balance_res = client.get_account_balance()
        if balance_res and balance_res.is_ok():
            body = balance_res.get_body()
            summary = body.get('output2', [{}])[0]
            cash_available = Decimal(summary.get('dnca_tot_amt', '0'))

            # Allocate 20% of available cash for this position
            position_budget = cash_available * Decimal('0.20')

            if latest_close > 0:
                buy_quantity = int(position_budget // Decimal(latest_close))
        else:
            logger.warning(f"Could not retrieve account balance for user {user}. Buy quantity set to 0.")

    except Exception as e:
        logger.error(f"Error calculating buy quantity for user {user}: {e}", exc_info=True)

    logger.info(f"Strategy for {symbol} ({horizon}): Buy {buy_quantity} shares, SL: {stop_loss_price:.2f}, TP: {target_price:.2f}")

    # 6. Return detailed result
    return DetailedStrategyResult(
        buy_quantity=buy_quantity,
        target_price=round(target_price, 2),
        stop_loss_price=round(stop_loss_price, 2),
        raw_data={'latest_close': latest_close, 'latest_atr': latest_atr}
    )


def analyze_stock(symbol: str, client: KISApiClient, market_trend: str = None) -> StockAnalysisResult:
    """
    Performs a comprehensive analysis of a stock.

    This function fetches historical data, calculates various technical indicators
    (RSI, MACD, Bollinger Bands, ATR), determines risk levels based on market
    trend, and uses Prophet to forecast future prices. It classifies the stock
    into an investment horizon ('SHORT', 'MID', 'LONG', or 'NONE').

    Args:
        symbol (str): The stock symbol to analyze.
        client (KISApiClient): An initialized KIS API client.
        market_trend (str, optional): The current market trend ('BULL', 'BEAR',
                                     'SIDEWAYS'). If None, it will be calculated.

    Returns:
        StockAnalysisResult | None: A data class with the analysis results,
                                    or None if the analysis fails.
    """
    logger.info(f"AI Service: Starting analysis for symbol {symbol}...")

    # 1. Fetch and prepare data
    try:
        history_response = client.get_daily_price_history(symbol, days=730)
        if not history_response or not history_response.is_ok():
            logger.error(f"Failed to fetch historical data for {symbol}: {history_response.get_error_message()}")
            return None

        price_history = history_response.get_body().get('output2')
        if not price_history:
            logger.warning(f"No historical data in response for {symbol}.")
            return None

        df = pd.DataFrame(price_history)
        df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d')
        numeric_cols = ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol', 'acml_tr_pbmn']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        df = df.set_index('stck_bsop_date').sort_index()
        df.rename(columns={'stck_oprc': 'open', 'stck_hgpr': 'high', 'stck_lwpr': 'low', 'stck_clpr': 'close', 'acml_vol': 'volume'}, inplace=True)
        df.dropna(inplace=True)

    except Exception as e:
        logger.error(f"Error processing data for {symbol}: {e}", exc_info=True)
        return None

    if df.empty:
        logger.warning(f"No historical data available for {symbol} after processing.")
        return None

    # 2. Technical Analysis with pandas_ta
    try:
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.atr(length=14, append=True)

        latest_indicators = df.iloc[-1]
        latest_close = latest_indicators['close']

        raw_data = {
            'latest_close': latest_close,
            'rsi_14': latest_indicators.get('RSI_14'),
            'macd_line': latest_indicators.get('MACD_12_26_9'),
            'macd_signal': latest_indicators.get('MACDs_12_26_9'),
            'macd_hist': latest_indicators.get('MACDh_12_26_9'),
            'bb_upper': latest_indicators.get('BBU_20_2.0'),
            'bb_lower': latest_indicators.get('BBL_20_2.0'),
            'latest_atr': latest_indicators.get('ATRr_14')
        }
    except Exception as e:
        logger.error(f"Failed to calculate technical indicators for {symbol}: {e}", exc_info=True)
        return None

    # 3. Risk Levels based on ATR and Market Trend
    if not market_trend:
        market_trend = get_market_trend(client)

    if market_trend == 'BULL':
        atr_multiplier = 2.5
    elif market_trend == 'BEAR':
        atr_multiplier = 1.5
    else: # SIDEWAYS
        atr_multiplier = 2.0

    stop_loss_price = latest_close - (atr_multiplier * raw_data['latest_atr'])
    target_price = latest_close + (2 * atr_multiplier * raw_data['latest_atr']) # Target is 2x risk
    raw_data['market_trend'] = market_trend
    raw_data['atr_multiplier'] = atr_multiplier

    # 4. Prophet Forecasting
    try:
        prophet_df = df.reset_index()[['stck_bsop_date', 'close']].rename(columns={'stck_bsop_date': 'ds', 'close': 'y'})
        model = Prophet(daily_seasonality=True)
        model.fit(prophet_df)
        future = model.make_future_dataframe(periods=90)
        forecast = model.predict(future)
        forecast_30d = forecast['yhat'].iloc[-60]
        forecast_90d = forecast['yhat'].iloc[-1]
        raw_data.update({
            'forecast_30d_yhat': forecast_30d,
            'forecast_90d_yhat': forecast_90d
        })
    except Exception as e:
        logger.warning(f"Prophet analysis failed for {symbol}: {e}. Horizon will be based on TA only.")
        forecast_30d = 0
        forecast_90d = 0


    # 5. Investment Horizon Classification
    horizon = "NONE"
    try:
        is_buy_signal = (
            raw_data['rsi_14'] < 70 and
            raw_data['macd_line'] > raw_data['macd_signal'] and
            latest_close > df['close'].rolling(window=50).mean().iloc[-1]
        )

        if is_buy_signal:
            if forecast_30d > latest_close * 1.05:
                horizon = "SHORT"
            elif forecast_90d > latest_close * 1.15:
                horizon = "MID"
            else:
                horizon = "SHORT"
        else:
            logger.info(f"No clear buy signal for {symbol} based on current TA rules.")

    except Exception as e:
        logger.error(f"Failed to classify investment horizon for {symbol}: {e}", exc_info=True)
        horizon = "NONE"

    logger.info(f"Analysis for {symbol} complete. Horizon: {horizon}, SL: {stop_loss_price:.2f}, TP: {target_price:.2f}")

    # 6. Return structured result
    return StockAnalysisResult(
        symbol=symbol,
        horizon=horizon,
        stop_loss_price=round(stop_loss_price, 2),
        target_price=round(target_price, 2),
        raw_data=raw_data
    )

def get_market_trend(client: KISApiClient) -> str:
    """
    Analyzes the overall market trend using a major index proxy (Samsung Electronics).

    It calculates 20, 60, and 120-day simple moving averages (SMAs) to
    determine if the market is in a bullish, bearish, or sideways trend.

    Args:
        client (KISApiClient): An initialized KIS API client.

    Returns:
        str: 'BULL', 'BEAR', or 'SIDEWAYS'. Defaults to 'SIDEWAYS' on error.
    """
    logger.info("Analyzing overall market trend...")
    try:
        # Using Samsung Electronics ('005930') as a proxy for the KOSPI index
        history_response = client.get_daily_price_history("005930", days=250)
        if not history_response or not history_response.is_ok():
            logger.error("Failed to fetch market index data for trend analysis.")
            return 'SIDEWAYS'

        price_history = history_response.get_body().get('output2')
        df = pd.DataFrame(price_history)
        df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d')
        df['stck_clpr'] = pd.to_numeric(df['stck_clpr'])
        df = df.set_index('stck_bsop_date').sort_index()

        df['sma_20'] = df['stck_clpr'].rolling(window=20).mean()
        df['sma_60'] = df['stck_clpr'].rolling(window=60).mean()
        df['sma_120'] = df['stck_clpr'].rolling(window=120).mean()

        latest = df.iloc[-1]

        if latest['sma_20'] > latest['sma_60'] and latest['sma_60'] > latest['sma_120']:
            logger.info("Market Trend: BULL")
            return 'BULL'
        elif latest['sma_20'] < latest['sma_60'] and latest['sma_60'] < latest['sma_120']:
            logger.info("Market Trend: BEAR")
            return 'BEAR'
        else:
            logger.info("Market Trend: SIDEWAYS")
            return 'SIDEWAYS'

    except Exception as e:
        logger.error(f"Error during market trend analysis: {e}", exc_info=True)
        return 'SIDEWAYS'

def recommend_strategy_allocations(market_trend: str) -> Dict[str, int]:
    """
    Recommends capital allocation percentages based on the market trend.

    Args:
        market_trend (str): The current market trend ('BULL', 'BEAR', 'SIDEWAYS').

    Returns:
        Dict[str, int]: A dictionary mapping strategy horizons to percentage
                        allocations (e.g., {'short_term': 40, 'mid_term': 40}).
    """
    if market_trend == 'BULL':
        return {'short_term': 40, 'mid_term': 40, 'long_term': 20}
    elif market_trend == 'BEAR':
        return {'short_term': 20, 'mid_term': 30, 'long_term': 50}
    else: # SIDEWAYS
        return {'short_term': 30, 'mid_term': 40, 'long_term': 30}
