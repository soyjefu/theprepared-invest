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
    symbol: str
    horizon: str
    stop_loss_price: float
    target_price: float
    raw_data: Dict[str, Any]

from decimal import Decimal

@dataclass
class DetailedStrategyResult:
    buy_quantity: int
    target_price: float
    stop_loss_price: float
    raw_data: Dict[str, Any]

def get_detailed_strategy(user, symbol: str, horizon: str) -> DetailedStrategyResult:
    """
    Generates a detailed, actionable trading strategy for a given stock and investment horizon,
    including a calculated buy quantity based on the user's available cash.
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

    # 2. Fetch and prepare data (same as analyze_stock)
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

    # 3. Technical Analysis (same as analyze_stock)
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

            # Use 20% of available cash for this position
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


def analyze_stock(symbol: str, client: KISApiClient) -> StockAnalysisResult:
    """
    Analyzes a stock's historical data to forecast future price, classify an investment
    horizon, and calculate risk management levels (stop-loss, target price).
    This upgraded version includes more technical indicators (RSI, MACD, Bollinger Bands).
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
        # Use standard column names for pandas_ta
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
        return None # Can't proceed without indicators

    # 3. Risk Levels based on ATR
    stop_loss_price = latest_close - (2 * raw_data['latest_atr'])
    target_price = latest_close + (4 * raw_data['latest_atr'])

    # 4. Prophet Forecasting (Optional but kept for trend analysis)
    try:
        prophet_df = df.reset_index()[['stck_bsop_date', 'close']].rename(columns={'stck_bsop_date': 'ds', 'close': 'y'})
        model = Prophet(daily_seasonality=True)
        model.fit(prophet_df)
        future = model.make_future_dataframe(periods=90) # Forecast shorter term
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


    # 5. Upgraded Investment Horizon Classification
    horizon = "NONE"
    try:
        # Conditions for a potential buy signal
        is_buy_signal = (
            raw_data['rsi_14'] < 70 and # Not overbought
            raw_data['macd_line'] > raw_data['macd_signal'] and # Bullish MACD crossover
            latest_close > df['close'].rolling(window=50).mean().iloc[-1] # Above 50-day MA
        )

        if is_buy_signal:
            # Classify based on Prophet's forecast strength if available
            if forecast_30d > latest_close * 1.05:
                horizon = "SHORT"
            elif forecast_90d > latest_close * 1.15:
                horizon = "MID"
            else: # If forecast is not strong, but TA is good, consider it short-term
                horizon = "SHORT"
        else:
            logger.info(f"No clear buy signal for {symbol} based on current TA rules.")

    except Exception as e:
        logger.error(f"Failed to classify investment horizon for {symbol}: {e}", exc_info=True)
        horizon = "NONE"

    logger.info(f"Analysis for {symbol} complete. Horizon: {horizon}, SL: {stop_loss_price:.2f}, TP: {target_price:.2f}, Indicators: {raw_data}")

    # 6. Return structured result
    return StockAnalysisResult(
        symbol=symbol,
        horizon=horizon,
        stop_loss_price=round(stop_loss_price, 2),
        target_price=round(target_price, 2),
        raw_data=raw_data
    )
