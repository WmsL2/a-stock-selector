# Backend

Python 3.12 backend for A Stock Selector. It contains the FastAPI read-only API, quant domain models, provider abstractions, local Parquet/DuckDB storage, bounded daily collection, structural universe, dated risk states, and point-in-time fundamentals/valuation/industry reporting.

Install from the workspace root with:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

From this directory, run tests and tooling with `..\.venv\Scripts\python.exe -m pytest`, `..\.venv\Scripts\ruff.exe check .`, and `..\.venv\Scripts\mypy.exe src`. Runtime data remains outside this source tree at `../runtime/`.

## Fundamentals, valuation, and industry history

- Financial records retain both `report_period` and the source notice date. The queryable
  `available_at` is a conservative Asia/Shanghai 15:30 timestamp on that notice date, so
  point-in-time reads never use a filing that was not yet public. Restatements are retained
  as separate `(symbol, report_period, available_at)` revisions. ROA maps specifically from
  AKShare `stock_financial_analysis_indicator_em.ZZCJLL` (总资产收益率(加权)(%)) and remains
  in percentage units (`3.25` means 3.25%).
- Valuation observations are dated daily series only. The current AKShare adapter supplies
  PE (TTM), PB, PCF, and total market cap; PE can remain negative, total market cap is
  converted from 亿元 to CNY, and unavailable PS/dividend/float-cap fields stay null.
- Industry history uses CNInfo change events and constructs inclusive effective intervals
  independently per classification. No pre-first-event history is invented. Collection is
  always explicit-symbol and is not an all-market bootstrap command.

## Factor Preprocessing

Task 10 provides generic, pure cross-sectional preprocessing; it does not calculate any
actual factor. Missing values are explicitly kept missing, imputed with the market median, or
imputed with the matching caller-provided industry median (with no implicit market fallback).
Prepared values are winsorized across the entire cross-section using
`median ± 3 × 1.4826 × MAD` by default; zero MAD and disabled winsorization preserve values.
Scores use average-rank percentiles on a 0–100 scale, retain ties, and assign 50 to a
single-observation group. Optional industry percentile mode ranks only within the explicit
`industry_key`; it does not look up any industry data or run regression neutralization.

## Five Factor Families

Quality uses ROE, ROA and gross/net margins. Value ranks positive-only `1/PE`, `1/PB` and
`1/PCF`; nonpositive multiples are unavailable. Growth is same-report-period YoY with a
strictly positive prior base. Quality, Value and Growth use industry percentiles; Momentum
(20/60 observation returns) and Low Volatility (20/60 `pstdev(returns) × sqrt(252) × 100`)
use market percentiles. Current operational RAW daily bars are never consumed: price factors
require a caller-provided `corporate_action_adjusted=True` series, which this task does not
manufacture or fetch.
