# VN30 Portfolio Optimization & Backtesting

Quantitative portfolio allocation strategies (Markowitz, Black-Litterman/ML-based) benchmarked via walk-forward backtesting on Vietnam's VN30 index - built with a survivorship-bias-free, point-in-time universe.

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
│       └── vn30_membership_point_in_time.json
├── notebooks/
│   ├── 01_data_collection.ipynb          # ✅ done
│   ├── 02_baseline_models.ipynb          # ⏳ next
│   ├── 03_advanced_allocation.ipynb
│   ├── 04_backtest_engine.ipynb
│   └── 05_evaluation_robustness.ipynb
├── src/                                  # reusable code (to be extracted from notebooks)
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
| **Rebalance frequency assumed** | Semi-annual (January & July HOSE reviews), plus any confirmed off-cycle replacements |

### Point-in-time universe construction

VN30 is reviewed twice a year, but composition can also change **mid-cycle** when a constituent is delisted, placed under trading control/suspension, goes bankrupt, or is merged/acquired — HOSE maintains a 10-stock reserve list for exactly this purpose.

To avoid survivorship bias, this project:
1. Collects every `ADD`/`REMOVE` event (with official effective date) from HOSE announcements and financial news, for both regular semi-annual reviews and confirmed off-cycle replacements.
2. Anchors the current (as of ~July 2026) VN30 list from `vnstock`.
3. Walks backward in time, "undoing" each ADD/REMOVE event, to reconstruct the exact 30-stock composition effective at every point in the 2019–2026 window.

**Coverage:** 12 regular semi-annual review periods (2019 T1 – 2025 T2) with confirmed composition changes, 3 periods confirmed as no-change (2022 T1, 2024 T1, 2024 T2), and 1 confirmed off-cycle event (DGC → BSR, effective 2026-05-13, due to DGC being placed under trading control).

## Data Quality & Limitations

- **ROS (FLC Faros):** removed from VN30 at the regular 2021-02-01 review, later force-delisted entirely from HOSE on 2022-09-05. Price series is legitimately sparse/truncated after delisting — excluded from any period where it wasn't an active VN30 constituent via the point-in-time membership table.
- **VPL (Vinpearl):** re-listed on HOSE on 2025-05-13 after an 14-year absence; price history before this date is legitimately unavailable (leading NaN), not a data error.
- **SSB (SeABank):** listed on HOSE on 2021-03-24; missing rate (~29.6%) is consistent with the pre-listing period and confirmed against the actual listing date.
- **Short gaps (<1% missing) in BCM, LPB, POW, BSR, VIB, GVR, DGC, ACB, SHB:** forward-filled with a 5-trading-day limit (`ffill(limit=5)`) to reflect short trading suspensions/holidays, without masking longer, more meaningful gaps.
- **Membership change sourcing:** effective dates and ADD/REMOVE events were collected via AI-assisted web search across financial news sources (Vietstock, VnEconomy, CafeF, DNSE, etc.) and cross-checked for logical consistency (ADD/REMOVE balance per period, no double-adds without an intervening remove). Not all periods have been verified against original HOSE decision documents — treat pre-2023 events as reasonably reliable but not certified against primary sources.
- **Outlier returns (>30%/day):** flagged programmatically during processing; each occurrence should be manually reviewed for corporate actions (stock splits, dividends) vs. genuine data errors before being used in optimization.

## Roadmap

| Sprint | Notebook | Status |
|---|---|---|
| Data collection & PIT universe construction | `01_data_collection.ipynb` | ✅ Done |
| Baseline allocation (Equal-weight, Market-cap-weight, Markowitz mean-variance) | `02_baseline_models.ipynb` | ⏳ Next |
| Advanced allocation (Black-Litterman or ML-based expected returns) | `03_advanced_allocation.ipynb` | Planned |
| Walk-forward backtest engine with transaction costs | `04_backtest_engine.ipynb` | Planned |
| Evaluation (Sharpe, Sortino, Max Drawdown, CAGR, turnover) & robustness checks | `05_evaluation_robustness.ipynb` | Planned |

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
