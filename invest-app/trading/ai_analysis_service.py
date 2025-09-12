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

def analyze_stock(symbol: str, client: KISApiClient) -> StockAnalysisResult:
    """
    Analyzes a stock's historical data to forecast future price, classify an investment
    horizon, and calculate risk management levels (stop-loss, target price).
    """
    logger.info(f"AI Service: Starting analysis for symbol {symbol}...")

    # 1. Fetch historical data
    try:
        # Fetching 2 years of data for a robust analysis
        history_response = client.get_daily_price_history(symbol, days=730)
        if not history_response or history_response.get('rt_cd') != '0' or not history_response.get('output2'):
            logger.error(f"Failed to fetch historical data for {symbol}: {history_response}")
            return None

        price_history = history_response['output2']
        df = pd.DataFrame(price_history)

        # Data Cleaning and Preparation
        df['stck_bsop_date'] = pd.to_datetime(df['stck_bsop_date'], format='%Y%m%d')
        numeric_cols = ['stck_clpr', 'stck_oprc', 'stck_hgpr', 'stck_lwpr', 'acml_vol']
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col])

        df = df.sort_values('stck_bsop_date').reset_index(drop=True)

    except Exception as e:
        logger.error(f"Error processing data for {symbol}: {e}")
        return None

    if df.empty:
        logger.warning(f"No historical data available for {symbol} after processing.")
        return None

    # 2. Format for Prophet
    prophet_df = df[['stck_bsop_date', 'stck_clpr']].rename(columns={'stck_bsop_date': 'ds', 'stck_clpr': 'y'})

    # 3. Run Prophet analysis
    model = Prophet(daily_seasonality=True)
    model.fit(prophet_df)
    future = model.make_future_dataframe(periods=365)
    forecast = model.predict(future)

    # 4. Calculate ATR and Risk Levels
    try:
        # Use pandas_ta to calculate ATR
        df.ta.atr(length=14, append=True)
        latest_atr = df['ATRr_14'].iloc[-1]
        latest_close = df['stck_clpr'].iloc[-1]

        stop_loss_price = latest_close - (2 * latest_atr)
        target_price = latest_close + (4 * latest_atr)
    except Exception as e:
        logger.error(f"Failed to calculate ATR for {symbol}: {e}")
        stop_loss_price = latest_close * 0.90 # Fallback to 10%
        target_price = latest_close * 1.20 # Fallback to 20%

    # 5. Classify Investment Horizon
    horizon = "NONE"
    try:
        current_price = forecast['yhat'].iloc[-365] # Price at the end of historical data
        forecast_30d = forecast['yhat'].iloc[-365 + 30]
        forecast_90d = forecast['yhat'].iloc[-365 + 90]
        forecast_365d = forecast['yhat'].iloc[-1]

        # Simple rules based on forecasted growth
        if (forecast_30d / current_price - 1) > 0.10:
            horizon = "SHORT"
        elif (forecast_90d / current_price - 1) > 0.20:
            horizon = "MID"
        elif (forecast_365d / current_price - 1) > 0.30:
            horizon = "LONG"
    except Exception as e:
        logger.error(f"Failed to classify investment horizon for {symbol}: {e}")
        horizon = "NONE"

    logger.info(f"Analysis for {symbol} complete. Horizon: {horizon}, SL: {stop_loss_price:.2f}, TP: {target_price:.2f}")

    # 6. Return structured result
    return StockAnalysisResult(
        symbol=symbol,
        horizon=horizon,
        stop_loss_price=round(stop_loss_price, 2),
        target_price=round(target_price, 2),
        raw_data={
            'latest_close': latest_close,
            'latest_atr': latest_atr,
            'forecast_30d_yhat': forecast_30d,
        }
    )
