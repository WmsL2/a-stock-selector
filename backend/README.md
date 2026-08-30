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

## BaseScore

Task 12 composes the completed five-family scores through the caller-supplied `FactorsConfig`:
Quality 0.30, Value 0.25, Growth 0.20, Momentum 0.15, and Low Volatility 0.10 by default.
An enabled family with no score is not treated as a zero: its configured weight is omitted from
the BaseScore denominator, and the weights of available enabled families are renormalized. For
example, when Quality=80, Value=70 and Growth=60 are available but Momentum and Low Volatility
are missing, BaseScore is `(80×0.30 + 70×0.25 + 60×0.20) / 0.75`.

`data_completeness` is the available enabled-family weight divided by all enabled-family weight.
`confidence` is the corresponding configured-weight average of available family component
coverage; it therefore cannot exceed completeness. `confidence_adjusted_score = BaseScore ×
confidence` is a supplemental conservative reference, not a replacement for BaseScore. The
engine returns the configured and renormalized weight plus weighted contribution for every family
in fixed order, and does not fetch data, filter securities, rank results or persist snapshots.

## Daily Selection

Task 12A provides a read-only, on-demand local pipeline: structural universe → exact-date
conservative risk eligibility → point-in-time financial, valuation and industry inputs → five
factor families → BaseScore → deterministic BaseScore ranking. Missing or unknown enabled risk
fields block official selection; incomplete risk coverage returns HTTP 200 readiness diagnostics
and an empty item list rather than treating an unknown security as safe.

The explicit industry policy is `证监会行业分类标准（2012）`, verified in the local CNInfo-derived
industry records. Its stable `classification:industry_code` becomes the factor industry key.
Current local daily bars are RAW only and are never represented as adjusted closes, so they do not
supply Momentum or Low Volatility. Quality, Value and Growth can still form a renormalized
BaseScore when their PIT inputs are available. The endpoint does not collect data, call providers,
persist selection snapshots, make recommendations or apply a minimum completeness threshold.

## Deterministic Explanation

Task 13 attaches structured `Evidence` and `RiskFlag` records to each already-ranked daily
selection item. Evidence is derived only from factor component values and scores, available
family scores, BaseScore contributions, data completeness and confidence. Family contribution
is expressed in BaseScore points, not as a percentage. The engine uses deterministic templates
and stable ordering, and never uses an LLM or free-form text generation.

The first RiskFlag set communicates data/model limitations only: unavailable or partially covered
families, low completeness, low confidence, and the current operational RAW-price limitation for
Momentum and LowVol. These flags do not change BaseScore, ranking, TopN, selection readiness or
risk eligibility. They are not investment recommendations and are generated on demand without
persistence, provider access or network calls. A future LLM layer, if introduced, may only
verbalize these structured records and must not invent evidence.
