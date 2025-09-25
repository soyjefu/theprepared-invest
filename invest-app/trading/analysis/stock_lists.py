"""
This module contains predefined lists of stock tickers for market analysis.

Note:
    These lists are static and for demonstration purposes. In a production
    environment, it is highly recommended to replace this with a dynamic
    approach, such as a daily Celery task that fetches the full list of
    market tickers from the brokerage API.
"""

# Example list of 20 major KOSPI 200 tickers.
KOSPI200_TICKERS = [
    "005930", "373220", "000660", "207940", "005935", "005380", "000270", 
    "068270", "005490", "035420", "006400", "051910", "035720", "003670", 
    "105560", "028260", "000810", "012330", "032830", "066570"
]

# Example list of 20 major KOSDAQ 150 tickers.
KOSDAQ150_TICKERS = [
    "247540", "086520", "091990", "451220", "196170", "066970", "353200", 
    "277810", "028300", "048220", "263750", "393890", "950130", "039030", 
    "214150", "042500", "067310", "214370", "095340", "086900"
]

def get_market_tickers():
    """
    Returns a combined list of all tickers to be targeted for analysis.

    This function aggregates the predefined KOSPI and KOSDAQ ticker lists
    and returns a unique set of symbols.

    Returns:
        list[str]: A list of unique stock symbols.
    """
    return list(set(KOSPI200_TICKERS + KOSDAQ150_TICKERS))