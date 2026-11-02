# KARZ — data validation and leakage checks for stock-screening backtests

KARZ is a small set of Python modules that inventory the price/fundamentals files behind a stock-screening
project, run data-quality and cross-source checks on them, scan analysis scripts for train/test leakage, and
provide one place (`data_config.py`) that defines chronological train/validation/test date splits. It targets
the owner's multi-market (India, US, China, Japan, Korea, Australia, Europe) screener data and produces JSON
reports plus helper functions for fair backtests.

> Status: maintained, research tooling. Educational use only; not investment advice. The figures quoted in the
> older docs (9M+ records, 40 sources, 86% quality) came from runs on a private local data tree that is not part
> of this repository, so they cannot be reproduced from a clone.

## What it does
- `data_validator.py` inventories parquet/CSV sources, runs null / duplicate / dtype / `high < low` / date-gap /
  staleness checks, scores each source, and writes a JSON report.
- `data_validator.py` also flags source lines that look like look-ahead (`shift(-n)`) or train/test contamination.
- `repo_data_analyzer.py` parses Python scripts with `ast` to map which scripts read/write which data files,
  whether they split train/test, and whether they test on samples.
- `data_config.py` holds the single definition of the date splits (TRAIN 2015-01-01..2021-12-31,
  VAL 2022, TEST 2023-01-01..2024-06-30), validation thresholds, freshness presets and the data-source registry.
- `backtest_weight_optimization.py` compares two weight sets for an 8-dimension score on the TEST split
  (precision, recall, F1, accuracy, buy/sell return spread).
- `backtest_weight_validation.py` builds a z-scored fundamentals composite and reports quintile performance.

## Quick start
```bash
git clone https://github.com/herrrickshaw/karz.git
cd karz
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pandas, numpy (parquet I/O also needs pyarrow)
python data_config.py                    # validates the configuration and prints it
python data_validator.py                 # needs a data tree, see Configuration
```

Using the helpers from your own project:

```python
from data_config import DataConfig, filter_data_by_split

train_df = filter_data_by_split(df, "date", split="train")
test_df = filter_data_by_split(df, "date", split="test")        # unseen data only
errors = DataConfig().validation.validate_dataframe(test_df)    # list of problems, [] if clean
```

## How it works
| Stage | Module | Output |
|---|---|---|
| Configure splits, rules, sources | `data_config.py` | `DataConfig`, `filter_data_by_split` |
| Inventory + validate data files | `data_validator.py` (`DataValidator`) | `/tmp/data_validation_report.json` |
| Pure checks (reusable) | `check_dataframe_quality`, `quality_score`, `scan_text_for_leakage` | lists of issue strings / dataclasses |
| Analyse scripts for split/sample habits | `repo_data_analyzer.py` | `/tmp/repo_data_analysis.json` |
| Backtest weight sets | `backtest_weight_optimization.py` | console report, optional CSV (`--export`) |
| Quintile check of a fundamentals composite | `backtest_weight_validation.py` | console table |

Design notes: splits are chronological (never random) so a backtest cannot look into the future; the checks are
heuristics that flag items for human review (the leakage scan reports mostly false positives by design); the
validator samples files and symbols in some places (see the `MAX_*` constants in `data_validator.py`).

## Repository layout
| Path | Purpose |
|---|---|
| `data_config.py` | Splits, rules, registry, `filter_data_by_split` |
| `data_validator.py` | `DataValidator`, quality / leakage helpers, Kaggle placeholders, lineage tracker |
| `repo_data_analyzer.py` | `RepositoryDataAnalyzer`, `DataSplitValidator` |
| `backtest_weight_optimization.py` | `WeightBacktester`, `evaluate_signals`, `backtest_from_data_source` |
| `backtest_weight_validation.py` | Composite-quintile validation (imports `correlation_analysis` from the parent screener project) |
| `tests/` | pytest suite; `tests/golden/baseline.json` pins outputs captured before the 2026-11 refactor |
| `*.md` guides | Longer write-ups: `DATA_VALIDATION_QUICKSTART.md`, `DATA_VALIDATION_GUIDE.md`, `DATA_VALIDATION_HONEST_SUMMARY.md`, `DATA_VALIDATION_IMPLEMENTATION_ROADMAP.md`, `FIXED_SCRIPTS_SUMMARY.md`, `IMPLEMENTATION_STATUS.md`, `BACKTEST_TEMPLATE_CHANGES.md`, `TEMPLATE_FIX_SUMMARY.md`, `HOW_TO_USE_WITH_AI.md` |
| `notebooks/colab_test.ipynb` | Colab smoke notebook |

## Data sources
No data is shipped. `DataSourceRegistry` in `data_config.py` expects `cache_seed/cleaned_long*.parquet` and
`cache_seed/fundamentals/` from the sibling screener project (`herrrickshaw/global-stock-screener`).
`data_validator.py` lists four Kaggle stock datasets as placeholders ("Not yet downloaded"); it does not call
the Kaggle API. Respect each dataset's own licence.

## Configuration
- Date splits, thresholds and universes: edit the class attributes in `data_config.py`.
- Data root: `DataValidator(base_path=...)` and `RepositoryDataAnalyzer(base_path=...)` default to the owner's local
  path `DEFAULT_BASE_PATH` (`/Users/umashankar/Downloads/code/python_files`); pass your own directory.
- Backtest CLIs: `--market`, `--data`, `--weight-set`, `--export`, `--no-split` (the TEST split is the default).
- No secrets or environment variables are needed.

## Testing
```bash
pip install pytest ruff pyarrow
pytest -q        # offline; uses synthetic frames and temp dirs
ruff check .
```

## Limitations and known issues
- 🔴 The cross-source close-price comparison in `DataValidator._compare_symbol_closes` raises internally
  (`pd.to_datetime` on a `set`) and the error is swallowed, so it reports 0 discrepancies even when sources differ.
  The "0 cross-source discrepancies" figure in older docs is therefore not evidence of agreement.
- 🔴 `evaluate_signals` computes true negatives with `~` on 0/1 integers, which yields negative counts, so the
  reported `tn` and `accuracy` are wrong (precision, recall, F1 and returns are unaffected). Pinned by an `xfail` test.
- `DataValidationRules.validate_dataframe` adds a `returns` column to the frame you pass in, and its extreme-move
  threshold compares a fractional return with `50` (percent), so it almost never fires.
- `filter_data_by_split` converts the date column to datetime in place.
- `backtest_weight_validation.py` cannot run standalone: `correlation_analysis` lives in the parent project.
- Pandas gotchas: `if df:` raises, and `x or default` keeps `NaN` (truthy). Use `df is None or df.empty` and `pd.notna(x)`.
- Treat leakage flags as a checklist, not an autopilot; the scan found 6 flags on the author's tree, mostly false positives.
- Reports are written under `/tmp`; the validator and analyzer sample files (first 30-100 scripts, first 20 symbols).

## Related repositories
- [`herrrickshaw/global-stock-screener`](https://github.com/herrrickshaw/global-stock-screener): the screener whose data these checks target.

## Licence
The previous README states "MIT License", but the repository contains no LICENSE file yet — treat as all rights
reserved until one is added.
