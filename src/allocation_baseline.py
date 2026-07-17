"""
src/allocation_baseline.py

The functions calculate baseline allocation (Equal-weight, Market-cap-weight) and
helper retrieve the list of codes at a specific point-in-time period — reusable
between notebooks 02, 03, 04, and 05.
"""

import pandas as pd
from vnstock import register_user, Company

# Register vnstock
register_user('vnstock_2d2225369316c09dd7eb5cb6e00a6a67')

def get_symbols_at_latest_period(pit_membership):
    """
    Get the list of VN30 tickers at the latest period in pit_membership
    Parameters
    ----------
    pit_membership : dict
        {pd.Timestamp: list[str]} — output từ load_week1_outputs()
 
    Returns
    -------
    symbols_at_period : list[str]
    latest_period : pd.Timestamp
    """
    latest_period = max(pit_membership.keys())
    symbols_at_period = pit_membership[latest_period]
    return symbols_at_period, latest_period

def get_symbols_at_period(pit_membership, target_date):
    """
    Get a list of VN30 codes valid AT a specific date 
    (not necessarily the latest period) - used when backtesting requires
    looking up data at different rebalancing points
    Parameters
    ----------
    pit_membership : dict
    target_date : pd.Timestamp or str

    Returns
    -------
    list[str] or None if target_date is before the first period with data
    """
    target_date = pd.Timestamp(target_date)
    valid_periods = [d for d in pit_membership.keys() if d <= target_date]
    if not valid_periods:
        return None
    latest_valid_period = max(valid_periods)
    return pit_membership[latest_valid_period]

def compute_equal_weights(symbols_at_period):
    """
    Equal weight for every ticker in the basket

    Returns
    -------
    pd.Series, index=symbol, values=weight
    """
    n = len(symbols_at_period)
    return pd.Series(1 / n, index=symbols_at_period)


def compute_market_caps(symbols_at_period, prices_pivot, verbose=True):
    """
    Calculate the current market cap for each stock = most recent 
    closing price (thousand VND) x 1000 x outstanding_shares (taken 
    from Company().overview())

    Parameters
    ----------
    symbols_at_period : list[str]
    prices_pivot : pd.DataFrame (index=date, columns=symbol, values=giá nghìn VND)
    verbose : bool - print error if cannot retrieve data

    Returns
    -------
    pd.Series, index=symbol, values=market cap (VND)
    """
    market_caps = {}
    for sym in symbols_at_period:
        try:
            company = Company(symbol=sym, source='KBS')
            overview = company.overview()
            outstanding_shares = int(overview['outstanding_shares'].values[0])

            # Closing price (unit: thousands of VND) at the latest date in the prices_pivot DataFrame
            latest_price_thousand_vnd = prices_pivot[sym].dropna().iloc[-1]
            latest_price_vnd = latest_price_thousand_vnd * 1000

            market_caps[sym] = latest_price_vnd * outstanding_shares
        except Exception as e:
            if verbose:
                print(f"Error fetching data for {sym}: {e}")

    return pd.Series(market_caps)

def compute_market_cap_weights(symbols_at_period, prices_pivot, verbose=True):
    """
    Weights are based on market cap
    (normalized so that the sum equals 1)
    
    Returns
    -------
    pd.Series, index=symbol, values=weight
    """
    market_caps = compute_market_caps(symbols_at_period, prices_pivot, verbose=verbose)
    return market_caps / market_caps.sum()


def get_outstanding_shares(symbols, verbose=True):
    """
    Fetch current outstanding shares for a list of symbols (fetched ONCE,
    reused across all backtest periods as a static proxy — vnstock does not
    provide historical outstanding share counts)

    Returns
    -------
    pd.Series, index=symbol, values=outstanding shares
    """
    shares = {}
    for sym in symbols:
        try:
            company = Company(symbol=sym)
            overview = company.overview()
            shares[sym] = overview['outstanding_shares'].values[0]
        except Exception as e:
            if verbose:
                print(f"Error fetching outstanding shares for {sym}: {e}")
    return pd.Series(shares)

def compute_market_caps_from_window(eligible_tickers, price_window, outstanding_shares):
    """
    Absolute market caps (VND) using the LAST price known within price_window
    (i.e. as of the rebalance date, no look-ahead) combined with static current
    outstanding shares.
 
    This is the single source of truth for market cap at a given rebalance
    date, used both to derive the Market-cap-weight benchmark (normalize by
    dividing by the sum) and as the direct input to
    `black_litterman.market_implied_prior_returns`, which requires absolute
    market cap values, not normalized weights.
 
    Parameters
    ----------
    eligible_tickers : list[str]
    price_window : pd.DataFrame, historical prices strictly before the rebalance date
    outstanding_shares : pd.SeriesSeries, pre-fetched once via get_outstanding_shares()
 
    Returns
    -------
    pd.Series, index=symbol, values=market cap (VND)
    """
    latest_price_vnd = price_window[eligible_tickers].iloc[-1] * 1000
    shares_subset = outstanding_shares.reindex(eligible_tickers).dropna()
    return latest_price_vnd[shares_subset.index] * shares_subset