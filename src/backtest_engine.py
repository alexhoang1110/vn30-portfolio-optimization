"""
src/backtest_engine.py

Week 4 - walk-forward backtest engine.

At every rebalance date, this module re-derives everything (active universe,
eligible tickers, market caps, covariance, momentum views, Black-Litterman
posterior) using ONLY data known strictly before that date - no look-ahead.
"""

import pandas as pd
from pypfopt import expected_returns, black_litterman
from pypfopt.black_litterman import BlackLittermanModel
from pypfopt.efficient_frontier import EfficientFrontier
from pypfopt.risk_models import CovarianceShrinkage

from src.allocation_baseline import (
    get_symbols_at_period,
    compute_equal_weights,
    compute_market_caps_from_window,
)

def get_estimation_data(rebalance_date, prices_pivot, pit_membership, window_years=2, min_required_days=253):
    """
    Get the active universe and its price history AS KNOWN AT rebalance_date,
    never uses any price data on or after rebalance_date (no look-ahead).

    min_required_days = 252 (momentum lookback) + 1, since this backtest uses
    simplified fixed-confidence Black-Litterman views (no per-period hit-rate
    validation, which would otherwise require +63 more days of forward buffer,
    as used in Week 3's one-off validation).

    Parameters
    ----------
    rebalance_date : pd.Timestamp
    prices_pivot : pd.DataFrame
    pit_membership : dict
    window_years : int - rolling estimation window length
    min_required_days : int - minimum continuous price history required for a
        ticker to be eligible for momentum-based views

    Returns
    -------
    price_window : pd.DataFrame, eligible tickers only, no NaN
    eligible : list[str]
    """
    active_symbols = get_symbols_at_period(pit_membership, rebalance_date)
    if active_symbols is None:
        return None, []
    
    window_start = rebalance_date - pd.DateOffset(years=window_years)
    price_window = prices_pivot.loc[window_start:rebalance_date, active_symbols]
    price_window = price_window[price_window.index < rebalance_date]  # exclude the rebalance day itself
    
    eligible = [
        s for s in active_symbols
        if price_window[s].dropna().shape[0] >= min_required_days
    ]

    return price_window[eligible].dropna(how='any'), eligible

def compute_weights_at_date(rebalance_date, prices_pivot, pit_membership, outstanding_shares, vn30_index, min_eligible=5, fixed_confidence=0.5):
    """
    Compute portfolio weights for all 4 strategies at a single rebalance date,
    using only information known strictly before that date.

    Parameters
    ----------
    rebalance_date : pd.Timestamp
    prices_pivot : pd.DataFrame
    pit_membership : dict
    outstanding_shares : dict
    vn30_index : pd.Series
    min_eligible : int - minimum number of eligible tickers required
    fixed_confidence : float, default 0.5 - confidence level for Black-Litterman views

    Returns
    -------
    dict[str, pd.Series] or None if too few eligible tickers to optimize
    """
    price_window, eligible = get_estimation_data(rebalance_date, prices_pivot, pit_membership)
    if price_window is None or len(eligible) < min_eligible:
        return None

    # Equal-weight
    eq_w = compute_equal_weights(eligible)

    # Market-cap-weight
    # Single source of truth for market cap at this rebalance date: absolute
    # VND values, reused for both the benchmark weight and the BL prior below.
    market_caps_window = compute_market_caps_from_window(eligible, price_window, outstanding_shares)
    if market_caps_window.empty:
        return None
    mc_w = market_caps_window / market_caps_window.sum()

    # Markowitz (max-Sharpe)
    S = CovarianceShrinkage(price_window).ledoit_wolf()
    mu = expected_returns.mean_historical_return(price_window)
    mw_w = pd.Series(EfficientFrontier(mu, S).max_sharpe())

    # Black-Litterman
    # Risk aversion (delta) estimated from VN30-Index data strictly before
    # rebalance_date - no look-ahead into future market sentiment.
    vn30_window = vn30_index.loc[:rebalance_date].iloc[:-1]
    delta = black_litterman.market_implied_risk_aversion(vn30_window, risk_free_rate=0.035)
    prior = black_litterman.market_implied_prior_returns(market_caps_window, delta, S)

    # Momentum-based views, recomputed fresh from price_window (this period's
    # top-momentum tickers may differ completely from other periods).
    momentum = price_window.pct_change(252).iloc[-1].dropna()
    top5 = momentum.sort_values(ascending=False).head(5)
    viewdict = (top5 / 10).to_dict()  # dampened, same as Week 3

    # Simplification vs. Week 3: fixed confidence per view instead of a
    # full hit-rate backtest at every rebalance date (too costly to repeat
    # for every period). Documented as a limitation in the README.
    bl = BlackLittermanModel(
        S, pi=prior, absolute_views=viewdict,
        omega='idzorek', view_confidences=[fixed_confidence] * len(viewdict)
    )
    ef_bl = EfficientFrontier(bl.bl_returns(), bl.bl_cov())
    # max_sharpe() already returns a dict keyed by the correct tickers -
    # do NOT reconstruct the index manually (risk of ticker/weight mismatch).
    bl_w = pd.Series(ef_bl.max_sharpe())

    return {
        'equal': eq_w,
        'market_cap': mc_w,
        'markowitz': mw_w,
        'black_litterman': bl_w,
    }

def compute_transaction_cost(old_weights, new_weights, brokerage_fee=0.002, sell_tax=0.001):
    """
    Turnover-based transaction cost. Buys incur brokerage fee only; sells
    incur BOTH brokerage fee and the 0.1% sell tax (VN market rule).

    Parameters
    ----------
    old_weights : pd.Series or None (None on the first rebalance date -> no cost)
    new_weights : pd.Series
    brokerage_fee : float
    sell_tax : float

    Returns
    -------
    float - cost as a fraction of portfolio value
    """
    if old_weights is None:
        return 0.0

    all_symbols = set(old_weights.index) | set(new_weights.index)
    old_w = old_weights.reindex(all_symbols, fill_value=0)
    new_w = new_weights.reindex(all_symbols, fill_value=0)

    delta = new_w - old_w
    buys = delta[delta > 0].sum()
    sells = -delta[delta < 0].sum()

    return buys * brokerage_fee + sells * (brokerage_fee + sell_tax)

def run_backtest(rebalance_dates, prices_pivot, pit_membership, outstanding_shares, vn30_index,
                  fixed_confidence=0.5, return_weights_history=False):
    """
    Walk-forward backtest loop across all 4 strategies.

    fixed_confidence : float, default 0.5 - forwarded to compute_weights_at_date;
        Week 5 uses this to test Black-Litterman's sensitivity to view confidence.
    return_weights_history : bool, default False - if True, also returns the
        full per-period weights for each strategy (needed for Week 5 turnover
        calculation and sensitivity analysis). Default False preserves the
        exact return signature used in 04_backtest_engine.ipynb.

    Parameters
    ----------
    rebalance_dates : list[pd.Timestamp] or pd.DatetimeIndex, sorted ascending
    prices_pivot, pit_membership, outstanding_shares, vn30_index : see above

    Returns
    -------
    pd.DataFrame - cumulative portfolio value (starting at 1.0) per strategy,
    indexed by rebalance date.
    If return_weights_history=True, returns a tuple (DataFrame, weights_history),
    where weights_history is dict[str, dict[pd.Timestamp, pd.Series]].
    """
    strategies = ['equal', 'market_cap', 'markowitz', 'black_litterman']
    portfolio_values = {s: [1.0] for s in strategies}
    weights_history = {s: {} for s in strategies}
    dates_log = [rebalance_dates[0]]
    prev_weights = {s: None for s in strategies}

    for i, rdate in enumerate(rebalance_dates[:-1]):
        next_rdate = rebalance_dates[i + 1]
        print(f"Processing {rdate.date()}...")

        weights_today = compute_weights_at_date(
            rdate, prices_pivot, pit_membership, outstanding_shares, vn30_index,
            fixed_confidence=fixed_confidence
        )
        if weights_today is None:
            print(f"  Skipped {rdate.date()} - insufficient eligible tickers.")
            continue

        # Realized return of each holding from rdate to next_rdate, using
        # prices AFTER the decision was made - correct, not look-ahead, since
        # the decision itself only used data strictly before rdate.
        period_prices = prices_pivot.loc[rdate:next_rdate]
        period_returns = period_prices.iloc[-1] / period_prices.iloc[0] - 1

        for strategy, w in weights_today.items():
            weights_history[strategy][rdate] = w
            gross_return = (w * period_returns.reindex(w.index).fillna(0)).sum()
            cost = compute_transaction_cost(prev_weights[strategy], w)
            net_growth = (1 + gross_return) * (1 - cost)
            portfolio_values[strategy].append(portfolio_values[strategy][-1] * net_growth)
            prev_weights[strategy] = w

        dates_log.append(next_rdate)

    results_df = pd.DataFrame(portfolio_values, index=dates_log)
    if return_weights_history:
        return results_df, weights_history
    return results_df