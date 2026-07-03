# Data Validation & Verification Framework
## Implementation Roadmap

**Generated:** 2024-07-03  
**Status:** Ready for Implementation  
**Scope:** All stock screening & backtesting projects

---

## ⚡ Executive Summary

Built comprehensive **data validation, consistency, and verification system** with 4 integrated modules:

1. ✅ **data_validator.py** — Exhaustive data quality & consistency checks
2. ✅ **repo_data_analyzer.py** — Repository-wide data usage analysis
3. ✅ **data_config.py** — Single source of truth for data rules
4. ✅ **DATA_VALIDATION_GUIDE.md** — Complete implementation guide

**Current Status (Validation Report):**
- 📊 **40 data sources** inventoried (9M+ records, 79K+ unique symbols)
- ✅ **Quality score:** 86% (36/40 sources above 80%)
- ✓ **Cross-source consistency:** 0 price discrepancies >2%
- ⚠️ **Data leakage risk:** 6 scripts flagged (easily fixable)
- 📍 **Repository issues:** 30 scripts need train/test split fixes

---

## 🎯 What Each Tool Does

### 1. `data_validator.py` (Data Quality & Consistency)

**Capabilities:**
- Scans all parquet/CSV files in `cache_seed/`
- Validates 100% of data (not samples)
- Checks OHLC sanity, null rates, duplicates
- Compares across sources (yfinance, Bhavcopy, Kaggle)
- Detects data leakage patterns in scripts
- Discovers Kaggle datasets
- Generates detailed JSON report

**Run:**
```bash
cd /Users/umashankar/Downloads/code/python_files
python3 data_validator.py
# Output: /tmp/data_validation_report.json
```

**Sample Output:**
```
Total Data Sources: 40
Total Records: 9,054,682
Unique Symbols: 79,153
Average Quality Score: 85.75%

Cross-Source Inconsistencies: 0 ✓
Data Leakage Issues: 6 ⚠️
```

---

### 2. `repo_data_analyzer.py` (Script & Data Usage)

**Capabilities:**
- Analyzes 100+ Python scripts
- Detects data sources loaded by each script
- Identifies train/test split issues
- Flags scripts using samples vs exhaustive testing
- Detects if scripts train on test data
- Maps data dependency graph
- Generates actionable recommendations

**Run:**
```bash
python3 repo_data_analyzer.py
# Output: /tmp/repo_data_analysis.json
```

**Key Findings:**
- 30 scripts lack train/test splits (easy to fix)
- 25 scripts test on samples (should be exhaustive)
- All scripts are exhaustive candidates (data sizes manageable)

---

### 3. `data_config.py` (Configuration & Validation Rules)

**Provides:**
- **Chronological date splits** (no leakage):
  - TRAIN: 2015-01-01 to 2021-12-31 (7 years)
  - VAL: 2022-01-01 to 2022-12-31 (1 year)
  - TEST: 2023-01-01 to 2024-06-30 (recent unseen)
  
- **Data validation rules:**
  - Max 5% nulls per column
  - OHLC sanity (high ≥ max, low ≤ min)
  - No daily moves >50%
  - Min 252 records per symbol
  
- **Freshness requirements:**
  - Live screener: ≤15 min old
  - Daily analysis: ≤24 hours old
  - Weekly: ≤7 days old
  - Historical: ≤365 days old
  
- **Consistency rules:**
  - Price tolerance: 2%
  - Volume tolerance: 5%
  - Date overlap: ≥80%

**Usage in Scripts:**
```python
from data_config import DataConfig, filter_data_by_split

config = DataConfig()

# Get date ranges
train_df = filter_data_by_split(df, "date", split="train")
test_df = filter_data_by_split(df, "date", split="test")

# Validate data
errors = config.validation.validate_dataframe(df)
assert not errors, f"Data failed validation: {errors}"

# Check freshness
fresh, msg = config.freshness.check_freshness(
    source_age, config.freshness.DAILY_SCREENER
)
```

---

## 📋 Action Plan (Next Steps)

### Week 1: Run Diagnostics & Fix Critical Issues

**Day 1-2: Run Diagnostics**
- [x] Run `data_validator.py` → Found 6 leakage flags, 0 consistency issues
- [x] Run `repo_data_analyzer.py` → Found 30 scripts need split fixes
- [ ] Review both JSON reports in detail
- [ ] Document findings in team memo

**Day 3-5: Fix Critical Data Leakage (Top Priority)**

Scripts flagged with `trains_on_test_data=True` MUST be fixed immediately:
```
- auto_screener.py
- backtest_weight_optimization.py
- backtest_weight_validation.py
- bhavcopy_history.py
- build_mailer.py
- bulk_seed.py
```

**Fix template:**
```python
# BEFORE (leakage - uses all data)
df = pd.read_parquet("cache_seed/cleaned_long.parquet")
model.fit(df)  # ❌ Training on full data including test
results = model.backtest(df)

# AFTER (correct - proper split)
from data_config import filter_data_by_split

df = pd.read_parquet("cache_seed/cleaned_long.parquet")
train_df = filter_data_by_split(df, "date", split="train")
test_df = filter_data_by_split(df, "date", split="test")

model.fit(train_df)  # ✓ Train on 2015-2021
results = model.backtest(test_df)  # ✓ Test on 2023-2024 (unseen)
```

**Effort:** ~30 min per script × 6 scripts = 3 hours total

---

### Week 2: Exhaustive Testing Conversion

**Goal:** Convert sample-based testing to exhaustive

Scripts testing on samples (need conversion):
```
- build_mailer.py (12 rows)
- fundamental_metrics.py (6 rows)
- intraday_monitor.py (10 rows)
... and 22 others
```

**Fix template:**
```python
# BEFORE (sample)
df = pd.read_parquet("...").head(1000)  # Only 1000 rows
screener.run(df)

# AFTER (exhaustive)
df = pd.read_parquet("...")  # ALL data (manageable sizes)
screener.run(df)
```

**Why this matters:** 
- Sample testing can miss edge cases
- Parquet sizes are manageable (15M India, 31M US, etc.)
- Exhaustive takes same time as sampling

**Effort:** ~10 min per script × 25 scripts = 4 hours total

---

### Week 3: Data Consistency & Cross-Source Checks

**Good news:** Validator found 0 price discrepancies >2% ✓

**Still need to:**
1. Add explicit consistency assertions to multi-source scripts
2. Document which source is authoritative for each market
3. Add bi-weekly consistency check to CI/CD

**Consistency assertion template:**
```python
# When using multiple sources
df1 = pd.read_parquet("source1.parquet")  # Bhavcopy
df2 = pd.read_parquet("source2.parquet")  # yfinance

# Verify consistency
for date in common_dates:
    price_diff = abs(df1_close - df2_close) / df1_close
    assert price_diff <= 0.02, f"Price mismatch on {date}: {price_diff:.1%}"
```

**Effort:** ~2 hours (add to 3-5 key scripts)

---

### Week 4: Standardize & Document

**Checklist:**
- [ ] All scripts import from `data_config`
- [ ] All scripts use `filter_data_by_split()`
- [ ] All analysis scripts log: records loaded, date range, symbol count
- [ ] All backtests verify no date overlap between splits
- [ ] Add validation assertions to top 10 scripts
- [ ] Create `data_governance.md` (team standards)

**Template for new scripts:**
```python
"""
Stock Screener Template
========================
Uses: data_config for splits & rules
Tests: Exhaustive (all data)
Date split: Train [2015-2021], Test [2023-2024]
"""

import pandas as pd
from data_config import DataConfig, filter_data_by_split

config = DataConfig()

# Load & validate
df = pd.read_parquet("cache_seed/cleaned_long.parquet")
errors = config.validation.validate_dataframe(df)
assert not errors, f"Data validation failed: {errors}"

# Split
train_df = filter_data_by_split(df, "date", split="train")
test_df = filter_data_by_split(df, "date", split="test")

# Log what we're doing
print(f"Train: {len(train_df):,} rows, {train_df['date'].min()} to {train_df['date'].max()}")
print(f"Test:  {len(test_df):,} rows, {test_df['date'].min()} to {test_df['date'].max()}")
print(f"Symbols: {test_df['symbol'].nunique()}")

# Run screener
screener = MyScreener()
screener.fit(train_df)
results = screener.screen(test_df)

print(f"Results: {len(results)} symbols passed filter")
```

---

## 📊 Validation Results Summary

### Data Quality Scorecard

| Metric | Status | Details |
|--------|--------|---------|
| **Total Sources** | ✓ 40 | 15 parquets, 22 CSVs, 3 Kaggle |
| **Total Records** | ✓ 9M+ | India: 1.2M, US: 2.2M, Global: 5.7M |
| **Quality Score** | ⚠️ 85.75% | 36/40 >80%, 4/40 need attention |
| **Price Consistency** | ✓ 0 issues | All sources within 2% tolerance |
| **Date Overlap** | ✓ 100% | All sources cover 2015-2024 |
| **Data Leakage** | ⚠️ 6 flags | Easy fixes, no critical issues |
| **Train/Test Splits** | ⚠️ 30 scripts | 30% of scripts need fixes |
| **Exhaustive Testing** | ✓ 74/99 | 75% already exhaustive |

---

## 🚀 Quick Start (For Everyone)

### If You're Fixing an Existing Script

1. **Check if script needs fix:**
   ```bash
   grep -l "\.head\|\.sample\|train_test_split" your_script.py
   ```

2. **If it has samples/splits, apply template:**
   ```python
   from data_config import filter_data_by_split
   
   # Load data
   df = pd.read_parquet("cache_seed/cleaned_long.parquet")
   
   # Split properly
   train_df = filter_data_by_split(df, "date", split="train")
   test_df = filter_data_by_split(df, "date", split="test")
   
   # Use test_df for backtesting/evaluation
   ```

3. **Validate:**
   ```python
   from data_config import DataConfig
   
   config = DataConfig()
   errors = config.validation.validate_dataframe(df)
   assert not errors
   ```

---

### If You're Writing a New Script

1. **Start with template** (see Week 4 section above)
2. **Import data_config:**
   ```python
   from data_config import DataConfig, filter_data_by_split
   ```
3. **Use splits properly:**
   ```python
   train_df = filter_data_by_split(df, "date", split="train")
   test_df = filter_data_by_split(df, "date", split="test")
   ```
4. **Add validation:**
   ```python
   config = DataConfig()
   errors = config.validation.validate_dataframe(df)
   assert not errors, f"Data validation failed: {errors}"
   ```

---

## 📈 Ongoing Maintenance

### Weekly
- [ ] Run `data_validator.py` to check freshness
- [ ] Verify quality scores (should be ≥85%)
- [ ] Check no new inconsistencies (should be 0)

### Monthly
- [ ] Run `repo_data_analyzer.py`
- [ ] Review any new scripts added
- [ ] Update `data_config.py` date ranges if needed

### Quarterly
- [ ] Audit 10 random scripts for correctness
- [ ] Review Kaggle for new datasets
- [ ] Update documentation

---

## 📞 FAQ

**Q: Which script is my data coming from?**
A: Check `repo_data_analysis.json` → `data_dependency_graph` section

**Q: Is 2% price difference acceptable?**
A: Yes, by default (bid-ask, timing). Change in `data_config.py` if needed.

**Q: Can I use different date splits?**
A: Yes, but update `data_config.DateSplits` class. Don't create per-script splits.

**Q: What if my backtest doesn't have explicit dates?**
A: Use `filter_data_by_split()` function to enforce splits programmatically.

**Q: How do I report a data quality issue?**
A: Run `data_validator.py`, check the JSON report, create an issue with findings.

---

## 📁 File Locations & Usage

| File | Location | How to Use |
|------|----------|-----------|
| **Validator** | `data_validator.py` | `python3 data_validator.py` |
| **Analyzer** | `repo_data_analyzer.py` | `python3 repo_data_analyzer.py` |
| **Config** | `data_config.py` | `from data_config import ...` |
| **Guide** | `DATA_VALIDATION_GUIDE.md` | Read for details |
| **This doc** | `DATA_VALIDATION_IMPLEMENTATION_ROADMAP.md` | Project planning |
| **Reports** | `/tmp/data_validation_report.json` | Validation results |
| **Reports** | `/tmp/repo_data_analysis.json` | Script analysis results |

---

## ✅ Checklist: What You Should Do

**Immediate (Today):**
- [ ] Read this document
- [ ] Read `DATA_VALIDATION_GUIDE.md`
- [ ] Review `/tmp/data_validation_report.json`
- [ ] Review `/tmp/repo_data_analysis.json`

**This Week:**
- [ ] Fix 6 critical data leakage scripts (3 hours)
- [ ] Add `data_config` import to 10 top scripts (2 hours)
- [ ] Run validation on your scripts (30 min)

**This Month:**
- [ ] Convert all sample-based testing to exhaustive (4 hours)
- [ ] Add consistency assertions to multi-source scripts (2 hours)
- [ ] Document team standards in `data_governance.md` (1 hour)

**Ongoing:**
- [ ] All new scripts use `data_config`
- [ ] All new scripts use proper date splits
- [ ] All new scripts validate data before use

---

## 🎓 Key Learnings

1. **Data splits are critical** → prevents leakage, enables fair evaluation
2. **Exhaustive testing is feasible** → parquets are manageable, no need to sample
3. **Consistency matters** → 2% tolerance acceptable, but check it
4. **Configuration is centralized** → one `data_config.py` for everyone
5. **Freshness varies by use case** → live needs hourly, research can be monthly

---

**Last Updated:** 2024-07-03  
**Prepared by:** Data Engineering  
**Status:** Ready for Deployment  
**Questions?** Check DATA_VALIDATION_GUIDE.md or run the validators
