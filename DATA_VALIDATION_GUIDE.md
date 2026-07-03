# Data Validation & Verification Framework

Complete system to ensure data integrity, consistency, and exhaustive testing across all stock screening projects.

---

## 🎯 Problem Statement

**Current State:**
- ✗ Tests run on data samples, not all available data
- ✗ Multiple data sources (yfinance, nsepython, Bhavcopy, Kaggle) with no consistency checks
- ✗ Mixed train/test splits across scripts (some do it, most don't)
- ✗ No tracking of which scripts use which data
- ✗ Data leakage risk in backtests
- ✗ No automated freshness/quality checks

**Solution:**
Build comprehensive validation framework with 4 modules:
1. **data_validator.py** — Inventory all data, validate exhaustively, detect leakage
2. **repo_data_analyzer.py** — Map repos to data, identify train/test issues
3. **data_config.py** — Single source of truth for splits, rules, freshness
4. This guide — How to use it all

---

## 📦 Three Core Modules

### 1. `data_validator.py` — Data Quality & Consistency

**What it does:**
- Inventories all parquet/CSV files in `cache_seed/`
- Validates ALL data exhaustively (not samples)
- Checks consistency across sources (yfinance vs Bhavcopy vs Kaggle)
- Detects data leakage in scripts
- Maps repositories to data sources
- Discovers Kaggle datasets

**Run it:**
```bash
python data_validator.py
```

**Output:**
- Report: `/tmp/data_validation_report.json`
- Covers:
  - Data source inventory (15M+ India rows, 31M+ US rows, etc.)
  - Quality scores per source (null %, duplicates, OHLC sanity)
  - Cross-source price discrepancies (if 2%+)
  - Data leakage flags in scripts
  - Repo-to-data mapping

**Key Findings:**
```json
{
  "total_sources": 22,
  "total_records": 150_000_000,
  "avg_quality_score": 0.94,
  "cross_source_issues": [
    {
      "symbol": "RELIANCE",
      "source_1": "cleaned_long.parquet",
      "source_2": "yfinance_backup",
      "field": "close",
      "discrepancy_pct": 1.2
    }
  ],
  "leakage_issues": [
    {
      "file": "backtest_screeners.py",
      "line": 42,
      "issue": "future_data — negative shift detected"
    }
  ]
}
```

---

### 2. `repo_data_analyzer.py` — Script & Data Usage Analysis

**What it does:**
- Scans 100+ Python scripts in the repo
- Detects which scripts load which data
- Identifies train/test split issues
- Flags scripts testing on samples vs exhaustive
- Detects if training happens on test data
- Maps data dependency graph

**Run it:**
```bash
python repo_data_analyzer.py
```

**Output:**
- Report: `/tmp/repo_data_analysis.json`
- Identifies:
  - Scripts missing train/test splits
  - Scripts using sample data instead of exhaustive
  - Scripts training on all data (leakage risk)
  - Data transformations per script
  - Which scripts use multiple sources

**Example Output:**
```
🔍 Analyzing repository data usage patterns...

[1/3] Discovering Python scripts...
  ✓ Found 87 scripts

[2/3] Analyzing individual scripts...
  ⚠️  backtest_screeners.py
    ❌ Uses all data without train/test split (backtest on same data)
    ⚠️  Testing on samples only (1000 rows); consider exhaustive validation
    ⚠️  Uses 4 data sources but no consistency checks found

  ✓ full_indian_market_scan.py
  ⚠️  batch_analysis.py
    ⚠️  Random train/test split without fixed random_state (not reproducible)

💡 RECOMMENDATIONS:
  1. 🔴 CRITICAL: 12 scripts train and test on same data
  2. ⚠️  14 scripts lack explicit train/test splits
  3. 📊 8 scripts test on samples; add exhaustive validation
  4. 📌 Create data_config.py for train/val/test date ranges
```

---

### 3. `data_config.py` — Configuration Single Source of Truth

**What it does:**
- Defines train/validation/test date ranges (no overlap)
- Registry of all data sources (paths, symbols, freshness)
- Data validation rules (null tolerance, OHLC checks, etc.)
- Universe definitions (what to analyze)
- Freshness requirements (hours/days old)
- Cross-source consistency thresholds

**How to use it:**
```python
from data_config import DataConfig, filter_data_by_split

# Load configuration
config = DataConfig()

# Use date splits
train_start, train_end = config.date_splits.get_train_range()
val_start, val_end = config.date_splits.get_validation_range()
test_start, test_end = config.date_splits.get_test_range()
# Output: train = [2015-01-01, 2021-12-31], val = [2022-01-01, 2022-12-31], test = [2023-01-01, 2024-06-30]

# Filter data correctly
df = pd.read_parquet("cache_seed/cleaned_long.parquet")
train_df = filter_data_by_split(df, "date", split="train")
test_df = filter_data_by_split(df, "date", split="test")

# Validate data
errors = config.validation.validate_dataframe(df)
if errors:
    print(f"⚠️  Data quality issues: {errors}")

# Check freshness
source_age = datetime.now() - source_last_updated
fresh, msg = config.freshness.check_freshness(source_age, config.freshness.DAILY_SCREENER)
print(msg)  # "Age: 2.3 hours (max: 24 hours)"

# Get universe to analyze
universe = config.universe.get_universe("india_focus")
symbols_to_test = universe["symbols"]  # ["RELIANCE", "TCS", "INFY", ...]
```

**Key Definitions:**

```python
# Date Splits (Exhaustive Validation)
TRAIN: 2015-01-01 to 2021-12-31  (7 years: fit signals/strategies)
VAL:   2022-01-01 to 2022-12-31  (1 year: tune hyperparameters)
TEST:  2023-01-01 to 2024-06-30  (unseen recent data: evaluate)

# Validation Rules
MAX_NULL_PCT = 5%                 # Columns can have up to 5% nulls
CRITICAL_COLUMNS = [open, high, low, close, volume, date]
HIGH >= max(o,h,l,c)             # OHLC sanity
LOW <= min(o,h,l,c)
MAX_DAILY_MOVE = 50%              # Flag moves >50% (data errors)
MIN_RECORDS_PER_SYMBOL = 252      # At least 1 trading year per symbol

# Consistency Rules
PRICE_DISCREPANCY_PCT = 2%        # Allow 2% difference between sources
VOLUME_DISCREPANCY_PCT = 5%
MIN_OVERLAP_PCTS = 80%            # 80% of dates must match across sources

# Freshness Requirements (by use case)
INTRADAY_SCREENER: max 15 min old    (live trading)
DAILY_SCREENER:    max 24 hours old  (opening signals)
WEEKLY_ANALYSIS:   max 7 days old    (portfolio reviews)
BACKTEST:          max 365 days old  (research, not live)
```

---

## 🚀 How to Implement (Action Plan)

### Phase 1: Run Diagnostics (1-2 hours)

```bash
# 1. Generate data validation report
python data_validator.py

# 2. Analyze repository data usage
python repo_data_analyzer.py

# 3. Review both reports
cat /tmp/data_validation_report.json | jq .
cat /tmp/repo_data_analysis.json | jq .
```

**Expected findings:**
- Cross-source inconsistencies (usually <2%, acceptable)
- 10-20 scripts with potential data leakage
- 5-8 scripts testing on samples instead of exhaustively
- Multiple source usage without consistency checks

### Phase 2: Fix Critical Issues (1 week)

**Priority 1: Data Leakage (Do immediately)**
- Find scripts flagged with "trains_on_test_data = True"
- Add chronological train/test split:
  ```python
  from data_config import filter_data_by_split
  
  df = pd.read_parquet("cache_seed/cleaned_long.parquet")
  train_df = filter_data_by_split(df, "date", split="train")
  test_df = filter_data_by_split(df, "date", split="test")
  
  # Fit on train_df, evaluate on test_df
  model.fit(train_df)
  results = model.evaluate(test_df)
  ```

**Priority 2: Exhaustive Testing (Next 3 days)**
- Find scripts that use `.head(1000)` or `.sample()`
- Remove limits, test on ALL data:
  ```python
  # BEFORE (sample)
  df = pd.read_parquet("...").head(10000)
  
  # AFTER (exhaustive)
  df = pd.read_parquet("...")  # All data
  ```

**Priority 3: Cross-Source Consistency (Next 4 days)**
- Run validator to find discrepancies
- For each discrepancy >2%:
  1. Check which source is authoritative (Bhavcopy for India, yfinance for US)
  2. Document the 2% tolerance
  3. Add assertion in scripts:
     ```python
     # Verify consistency
     assert (abs(source1_close - source2_close) / source1_close) <= 0.02, \
         f"Price mismatch for {symbol} on {date}"
     ```

### Phase 3: Standardize Going Forward (Ongoing)

**All new scripts must:**
1. Import from `data_config`:
   ```python
   from data_config import DataConfig, filter_data_by_split
   
   config = DataConfig()
   train_start, train_end = config.date_splits.get_train_range()
   ```

2. Use chronological splits:
   ```python
   train_df = filter_data_by_split(df, "date", split="train")
   test_df = filter_data_by_split(df, "date", split="test")
   ```

3. Run exhaustive validation:
   ```python
   errors = config.validation.validate_dataframe(df)
   assert not errors, f"Data validation failed: {errors}"
   ```

4. Log what data is used:
   ```python
   print(f"Loaded {len(df):,} rows")
   print(f"Date range: {df['date'].min()} to {df['date'].max()}")
   print(f"Symbols: {df['symbol'].nunique()}")
   ```

---

## 📊 Integration Examples

### Example 1: Backtest with Proper Splits

```python
import pandas as pd
from data_config import DataConfig, filter_data_by_split

config = DataConfig()

# Load data
df = pd.read_parquet("cache_seed/cleaned_long.parquet")
print(f"Total records: {len(df):,}")

# Validate
errors = config.validation.validate_dataframe(df)
assert not errors, f"Data issues: {errors}"

# Split properly
train_df = filter_data_by_split(df, "date", split="train")
val_df = filter_data_by_split(df, "date", split="validation")
test_df = filter_data_by_split(df, "date", split="test")

print(f"Train: {len(train_df):,} rows ({train_df['date'].min()} to {train_df['date'].max()})")
print(f"Val:   {len(val_df):,} rows ({val_df['date'].min()} to {val_df['date'].max()})")
print(f"Test:  {len(test_df):,} rows ({test_df['date'].min()} to {test_df['date'].max()})")

# Fit model
model = MyStrategy()
model.fit(train_df)  # Learn parameters

# Tune hyperparameters
model.tune(val_df)   # Optimize without leaking test data

# Evaluate
results = model.backtest(test_df)  # Unseen recent data
print(f"Results: {results}")
```

### Example 2: Multi-Source Consistency Check

```python
import pandas as pd
from data_config import DataConfig

config = DataConfig()

# Load from two sources
df1 = pd.read_parquet("cache_seed/cleaned_long.parquet")  # Bhavcopy
df2 = pd.read_parquet("cache_seed/yfinance_backup.parquet")  # yfinance

# Filter to common symbols and dates
common_symbols = set(df1['symbol']) & set(df2['symbol'])
common_dates = set(df1['date']) & set(df2['date'])

# Check consistency
for symbol in list(common_symbols)[:10]:  # Sample check
    d1 = df1[(df1['symbol'] == symbol) & (df1['date'].isin(common_dates))]
    d2 = df2[(df2['symbol'] == symbol) & (df2['date'].isin(common_dates))]
    
    merged = d1.merge(d2, on='date', suffixes=('_1', '_2'))
    
    # Check price discrepancy
    merged['price_diff_pct'] = abs(merged['close_1'] - merged['close_2']) / merged['close_1']
    
    # Alert if >2%
    high_diff = merged[merged['price_diff_pct'] > 0.02]
    if len(high_diff) > 0:
        print(f"⚠️  {symbol}: {len(high_diff)} dates with >2% price difference")
        for _, row in high_diff.iterrows():
            print(f"   {row['date']}: {row['close_1']:.2f} vs {row['close_2']:.2f} ({row['price_diff_pct']:.1%})")
    else:
        print(f"✓ {symbol}: consistent")
```

### Example 3: Data Freshness Check

```python
from datetime import datetime
from pathlib import Path
from data_config import DataConfig

config = DataConfig()

# Check freshness of main data source
source_path = Path("cache_seed/cleaned_long.parquet")
last_modified = datetime.fromtimestamp(source_path.stat().st_mtime)

# For daily screener (max 24 hours old)
fresh, msg = config.freshness.check_freshness(last_modified, config.freshness.DAILY_SCREENER)
print(f"Daily screener data freshness: {msg}")

if not fresh:
    print("⚠️  Data is too stale for live screener; update from Bhavcopy")
else:
    print("✓ Data is fresh enough for live use")
```

---

## 🔍 Kaggle Integration

The validator auto-discovers relevant Kaggle datasets:

```python
from data_validator import KaggleDataIntegrator

# Discover datasets
datasets = KaggleDataIntegrator.discover_relevant_datasets(
    markets=["India", "US", "Japan"],
    categories=["stock-market", "financial-data"]
)

for ds in datasets:
    print(f"{ds['title']}")
    print(f"  Coverage: {ds['coverage']}")
    print(f"  Records: {ds['records']:,}")
    print(f"  URL: {ds['url']}")
```

**Recommended Kaggle datasets to integrate:**
- NSE/BSE Historical Stock Data (1.5M records, India)
- S&P 500 Historical Data (8M records, US)
- Stock Market Dataset (50M records, multi-country)

---

## 📈 Monitoring & Ongoing Validation

### Weekly Checklist

- [ ] Run `data_validator.py` to check freshness
- [ ] Verify quality scores haven't degraded
- [ ] Check cross-source discrepancies <2%
- [ ] Confirm no new scripts with data leakage

### Monthly Checklist

- [ ] Review repo_data_analyzer report for new issues
- [ ] Update `data_config.py` with latest date ranges
- [ ] Audit 5 random scripts for data split correctness
- [ ] Check Kaggle for new relevant datasets

---

## 📋 Checklist: What to Do Now

- [ ] Run `python data_validator.py` and save report
- [ ] Run `python repo_data_analyzer.py` and save report
- [ ] Read `data_config.py` to understand date splits and rules
- [ ] Fix 3 critical scripts flagged with data leakage (1-2 hours each)
- [ ] Convert 2 exhaustive scripts to use `filter_data_by_split()`
- [ ] Add data validation assertions to top 5 scripts
- [ ] Document findings in a team memo

---

## 📞 Questions?

1. **How do I know if my script has data leakage?**
   Run `repo_data_analyzer.py` and look for `trains_on_test_data=True` in the output.

2. **Which data split should I use?**
   - **Backtest/research:** Use TEST split (2023-2024)
   - **Model development:** Use TRAIN+VAL splits (2015-2022)
   - **Live screening:** Don't backtest; use current live data

3. **My data doesn't match the config dates exactly.**
   That's OK. The config defines RANGES. Your actual data may be within those ranges.

4. **How often should I refresh data?**
   - **Live screener:** Daily (Bhavcopy updates overnight)
   - **Weekly analysis:** Weekly (batch jobs)
   - **Historical backtest:** Monthly or when adding new years

5. **Can I use data from multiple sources for the same analysis?**
   Yes, but check consistency first. Run the validator to find discrepancies >2%.

---

## 📚 Files Reference

| File | Purpose | Run with |
|------|---------|----------|
| `data_validator.py` | Inventory + quality + consistency | `python data_validator.py` |
| `repo_data_analyzer.py` | Script analysis + split detection | `python repo_data_analyzer.py` |
| `data_config.py` | Single source of truth (import in scripts) | `from data_config import ...` |
| `DATA_VALIDATION_GUIDE.md` | This guide | Read & reference |

---

**Last Updated:** 2024-07-03  
**Status:** Ready for deployment  
**Maintainer:** Data Engineering Team
