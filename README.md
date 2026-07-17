# VN30 Portfolio Optimization & Backtesting

Quantitative portfolio allocation strategies (Equal-weight, Market-cap-weight, Markowitz, Black-Litterman) benchmarked via walk-forward backtesting on Vietnam's VN30 index — built with a survivorship-bias-free, point-in-time universe.

## Motivation

Most student-level portfolio projects on VN30 use the *current* basket of 30 stocks applied retroactively across the backtest period — this introduces **survivorship bias**, since stocks that were removed from the index (due to poor performance, delisting, control status, etc.) are silently excluded, inflating historical returns.
 
This project instead reconstructs the **point-in-time (PIT) composition** of VN30 across every review period from 2019 to 2026, so that at each rebalance date, the optimizer only ever "sees" the stocks that were actually in the index at that time.

## Project Structure

```
vn30-portfolio-optimization/
├── data/
│   ├── raw/                              # untouched source data
│   │   ├── vn30_membership_changes.csv   # manually/AI-collected ADD/REMOVE events per review period
│   │   └── vn30_all_prices_raw.csv       # raw price panel from vnstock
│   └── processed/                        # cleaned, analysis-ready outputs
│       ├── vn30_prices_processed.csv
│       ├── vn30_log_returns_processed.csv
│       ├── vn30_index_prices_processed.csv   # VN30-Index, used as the market proxy in Black-Litterman
│       ├── vn30_membership_point_in_time.json
│       ├── week3_allocation_weights.csv
│       ├── week4_backtest_results.csv
│       ├── week4_metrics_summary.csv
│       ├── week4_drawdowns.csv
│       ├── week4_drawdown_summary.csv
│       └── week4_hhi_over_time.csv
├── notebooks/
│   ├── 01_data_collection.ipynb          # ✅ done
│   ├── 02_baseline_models.ipynb          # ✅ done
│   ├── 03_advanced_allocation.ipynb      # ✅ done
│   ├── 04_backtest_engine.ipynb          # ✅ done
│   └── 05_evaluation_robustness.ipynb    # ⏳ next
├── src/                                  # reusable code, extracted from notebooks
│   ├── data_loader.py                    # loads all Week 1 processed outputs
│   ├── allocation_baseline.py            # equal/market-cap weights, PIT symbol lookups
│   └── backtest_engine.py                # walk-forward estimation, weights, transaction cost, backtest loop
├── outputs/                              # charts, result tables
└── README.md
```
## Data

| | |
|---|---|
| **Source** | [`vnstock`](https://github.com/thinh-vu/vnstock) (KBS provider for price history, VCI for listing) |
| **Period** | 2019-01-01 → 2026-07-01 |
| **Price unit** | Closing price in thousand VND (`'000 VND`) |
| **Universe** | 51 unique symbols — union of the current VN30 constituents and every symbol that has ever entered/left the index between 2019–2026 |
| **Market proxy** | VN30-Index (HOSE), used to estimate risk aversion (δ) for Black-Litterman — matches the exact optimization universe, rather than a broader index (VN-Index) or a single stock |
| **Rebalance frequency assumed** | Semi-annual (January & July HOSE reviews), plus any confirmed off-cycle replacements |

### Point-in-time universe construction

VN30 is reviewed twice a year, but composition can also change **mid-cycle** when a constituent is delisted, placed under trading control/suspension, goes bankrupt, or is merged/acquired — HOSE maintains a 10-stock reserve list for exactly this purpose.
 
To avoid survivorship bias, this project:
1. Collects every `ADD`/`REMOVE` event (with official effective date) from HOSE announcements and financial news, for both regular semi-annual reviews and confirmed off-cycle replacements.
2. Anchors the current (as of ~July 2026) VN30 list from `vnstock`.
3. Walks backward in time, "undoing" each ADD/REMOVE event, to reconstruct the exact 30-stock composition effective at every point in the 2019–2026 window.

**Coverage:** 12 regular semi-annual review periods (2019 T1 – 2025 T2) with confirmed composition changes, 3 periods confirmed as no-change (2022 T1, 2024 T1, 2024 T2), and 1 confirmed off-cycle event (DGC → BSR, effective 2026-05-13, due to DGC being placed under trading control).

## Methodology

### Baseline allocation (Week 2)

Three benchmark strategies computed on the latest point-in-time VN30 universe:
- **Equal-weight:** 1/N across all constituents.
- **Market-cap-weight:** current outstanding shares × historical closing price, used as a fixed proxy (does not track historical capital increases/buybacks — acceptable simplification for a baseline, revisited if needed in the backtest stage).
- **Mean-variance (Markowitz), max-Sharpe:** `PyPortfolioOpt`'s `EfficientFrontier`, with a Ledoit-Wolf shrinkage covariance estimator instead of the raw sample covariance to reduce estimation noise.

### Advanced allocation (Week 3)

Rather than relying purely on historical mean returns (noisy and unstable as optimizer input), this project uses the Black-Litterman model to blend two sources of information:
 
1. **Market-implied prior (π):** expected returns are reverse-engineered from the current market-cap weights via `market_implied_prior_returns` — i.e., "what returns would make today's market-cap weighting rational."
2. **Views:** absolute views on a subset of tickers, derived from 12-month price momentum, dampened (`/10`) before being fed into the model so they aren't taken at face value as literal expected returns.
3. **View confidence (Omega), via Idzorek's method:** instead of hand-setting the Omega uncertainty matrix directly (hard to interpret), each view's confidence (0-90%) is set using `omega='idzorek'`. Confidence is **not** set proportionally to raw momentum magnitude — it is derived from a **hit-rate backtest**: for each candidate ticker, we check historically how often the sign of 12-month momentum matched the sign of the following quarter's return. Tickers with a hit rate at or below 50% (no better than a coin flip) receive zero confidence; confidence scales with the statistical edge above 50%, capped at 90%.
This ties view reliability to a testable historical property of the signal, rather than to the analyst's subjective conviction or to the signal's raw magnitude — reducing (but not eliminating) the risk of a confidently-wrong view dominating the posterior.

### Walk-forward backtest (Week 4)
 
The Week 3 pipeline (baseline weights + Black-Litterman) is re-run **fresh at every quarterly rebalance date** from 2021-01-01 to 2026-07-01 (23 periods), using only information known strictly before each date:
 
- **Active universe:** looked up from the point-in-time membership table for that specific date, not the current 30 constituents.
- **Estimation window:** a rolling 2-year lookback of prices ending strictly before the rebalance date (no data on or after that date is used).
- **Eligibility filter:** at each rebalance date, tickers without enough continuous price history (≥253 trading days) within the window are excluded from momentum-based views — re-evaluated fresh every period (e.g. VPL only becomes eligible once it has accumulated enough post-relisting history).
- **Market cap:** computed from the price known at each rebalance date combined with static current outstanding shares (see Limitations) — a single source of truth reused for both the Market-cap-weight benchmark and the Black-Litterman prior at that date.
- **Risk aversion (δ):** re-estimated from the VN30-Index using only its price history strictly before the rebalance date.
- **View confidence simplification:** unlike the one-off Week 3 hit-rate validation, view confidence in the backtest loop is fixed at 50% for every view at every period, rather than re-running the full hit-rate backtest at each of the 23 rebalance dates (computationally expensive). This is a documented simplification, not an oversight — see Limitations.
- **Transaction costs:** turnover-based, using a 0.2% brokerage fee on both buys and sells, plus an additional 0.1% sell tax (VN market rule) applied only to sell transactions.
## Results (Week 4 — preliminary, pre-robustness-check)
 
Backtest period: 2021-01-01 to 2026-07-01, quarterly rebalancing, 23 periods, net of transaction costs.
 
| Strategy | CAGR | Volatility | Sharpe | Max Drawdown | Calmar |
|---|---|---|---|---|---|
| Equal-weight | 10.1% | 18.5% | 0.424 | -29.9% | 0.338 |
| Market-cap-weight | 10.0% | 20.5% | 0.392 | -30.5% | 0.327 |
| Markowitz (max-Sharpe) | 10.3% | 48.4% | 0.364 | -68.6% | 0.151 |
| Black-Litterman | 17.2% | 30.4% | 0.547 | -27.4% | 0.627 |
 
### Portfolio concentration (Herfindahl index)
 
Pure Markowitz mean-variance optimization repeatedly produced extreme concentration throughout the backtest, with its Herfindahl index exceeding 0.5 in roughly a third of the 23 rebalance periods, peaking near 1.0 in early 2023 (essentially a single-stock portfolio) and again near 0.9 in mid-2024. This directly explains Markowitz's -68.6% maximum drawdown, which had not recovered by the end of the backtest window: at the 2024-01-01 rebalance specifically, 84.3% of the portfolio was allocated to a single stock (FPT), driven by a noisy short-window covariance estimate that made the optimizer treat it as a near risk-free bet.
 
Black-Litterman, by anchoring expected returns to the market-implied equilibrium prior before incorporating momentum-based views, kept concentration substantially lower for most of the backtest (Herfindahl index typically 0.05-0.10) — notably, at the same 2024-01-01 rebalance where Markowitz went to 84% FPT, FPT was *also* one of Black-Litterman's momentum-selected views, yet the model did not concentrate the portfolio around it, illustrating how the equilibrium anchor tempers extreme single-view bets even when both methods are fed the same underlying signal. Concentration did rise later in the backtest (peaking around 0.41 in early 2026), driven by momentum views repeatedly favoring a correlated pair of stocks (VIC, VHM) for four consecutive quarters — still far below Markowitz's peak, but a correlated-position risk worth flagging given the two stocks' shared group affiliation.
 
⚠️ **Preliminary — not yet stress-tested.** Black-Litterman's outperformance coincides with a small number of large, sustained trends captured by its momentum views (FPT 2022-2025, VIC/VHM 2025-2026) and uses fixed 50% view confidence rather than per-period hit-rate validation. With only 23 rebalance periods, the statistical significance of any performance difference between strategies is low. Robustness checks — confidence sensitivity, alternative lookback windows, and the concentrated VIC/VHM position — are planned for Week 5 before drawing final conclusions.

## Data Quality & Limitations
 
- **ROS (FLC Faros):** removed from VN30 at the regular 2021-02-01 review, later force-delisted entirely from HOSE on 2022-09-05. Price series is legitimately sparse/truncated after delisting — excluded from any period where it wasn't an active VN30 constituent via the point-in-time membership table.
- **VPL (Vinpearl):** re-listed on HOSE on 2025-05-13 after an 14-year absence; price history before this date is legitimately unavailable (leading NaN), not a data error.
- **SSB (SeABank):** listed on HOSE on 2021-03-24; missing rate (~29.6%) is consistent with the pre-listing period and confirmed against the actual listing date.
- **Short gaps (<1% missing) in BCM, LPB, POW, BSR, VIB, GVR, DGC, ACB, SHB:** forward-filled with a 5-trading-day limit (`ffill(limit=5)`) to reflect short trading suspensions/holidays, without masking longer, more meaningful gaps.
- **Membership change sourcing:** effective dates and ADD/REMOVE events were collected via AI-assisted web search across financial news sources (Vietstock, VnEconomy, CafeF, DNSE, etc.) and cross-checked for logical consistency (ADD/REMOVE balance per period, no double-adds without an intervening remove). Not all periods have been verified against original HOSE decision documents — treat pre-2023 events as reasonably reliable but not certified against primary sources.
- **Outlier returns (>30%/day):** flagged programmatically during processing; each occurrence should be manually reviewed for corporate actions (stock splits, dividends) vs. genuine data errors before being used in optimization.
- **View confidence in the Black-Litterman step is a modeling choice, not ground truth:** the hit-rate validation only checks whether the momentum *signal* has historically had a statistical edge — it does not guarantee any individual view is correct going forward. Sensitivity of the resulting weights to the confidence levels is planned to be stress-tested in the Week 5 robustness checks (re-running with confidence ±20%).
- **Market-cap-weight and market-implied prior returns both use current (not historical) outstanding shares** as a simplification — see Methodology above.
- **Backtest view confidence is fixed at 50% for every period**, not re-validated via hit-rate at each rebalance date (computationally expensive to repeat 23 times) — a real simplification relative to the Week 3 one-off validation. Confidence sensitivity is planned to be stress-tested in Week 5.
- **Backtest sample size is small (23 quarterly rebalances)** — any observed performance ranking between strategies should be treated as suggestive, not statistically conclusive, until significance is checked in Week 5.
- **Black-Litterman's late-backtest concentration (VIC, VHM, ~2025-2026)** reflects two related, correlated stocks rather than a diversified set of momentum winners — a risk not fully captured by the Herfindahl index alone, since it doesn't account for cross-asset correlation.

## Roadmap

| Sprint | Notebook | Status |
|---|---|---|
| Data collection & PIT universe construction | `01_data_collection.ipynb` | ✅ Done |
| Baseline allocation (Equal-weight, Market-cap-weight, Markowitz mean-variance) | `02_baseline_models.ipynb` | ✅ Done |
| Advanced allocation (Black-Litterman, momentum-based views with hit-rate-validated confidence) | `03_advanced_allocation.ipynb` | ✅ Done |
| Walk-forward backtest engine with transaction costs | `04_backtest_engine.ipynb` | ✅ Done |
| Evaluation (Sharpe, Sortino, Max Drawdown, CAGR, turnover) & robustness checks | `05_evaluation_robustness.ipynb` | ⏳ Next |

## Requirements
 
```
pandas
numpy
matplotlib
seaborn
vnstock
PyPortfolioOpt
vectorbt
scipy
jupyter
```
 
## Author
 
Built as part of a personal portfolio project ahead of Data Analyst / Data Scientist and Quant Research internship applications.
