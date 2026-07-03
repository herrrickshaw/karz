# Backtest Script Template — Before & After

This shows exactly how to fix `backtest_weight_optimization.py` and the pattern to apply to similar scripts.

---

## 🔄 Changes Made

### 1. **Add Imports** (Top of file)

**BEFORE:**
```python
#!/usr/bin/env python3
"""Backtest Framework..."""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List
from datetime import datetime, timedelta
```

**AFTER:**
```python
#!/usr/bin/env python3
"""Backtest Framework..."""

import pandas as pd
import numpy as np
from typing import Dict, Tuple, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
import argparse

# NEW: Import data configuration for proper splits
try:
    from data_config import DataConfig, filter_data_by_split
    HAS_DATA_CONFIG = True
except ImportError:
    HAS_DATA_CONFIG = False
    print("⚠️  data_config.py not found.")
```

**Why:** Enables train/test split support and graceful fallback if data_config not available.

---

### 2. **Update __init__ Method** (Constructor)

**BEFORE:**
```python
def __init__(self, data_df: pd.DataFrame, lookback_years: int = 3):
    """Initialize backtest framework"""
    self.data = data_df.copy()
    self.lookback_years = lookback_years
    self.results = {}

    print(f"\n📊 BACKTEST INITIALIZATION")
    print(f"   Companies: {len(self.data):,}")
    print(f"   Lookback period: {lookback_years} years")
    print(f"   Date range: {datetime.now().date() - timedelta(days=365*lookback_years)} to {datetime.now().date()}")
```

**AFTER:**
```python
def __init__(self, data_df: pd.DataFrame, lookback_years: int = 3, use_test_split: bool = False):
    """Initialize backtest framework with optional data validation"""
    self.data = data_df.copy()
    self.lookback_years = lookback_years
    self.results = {}
    self.use_test_split = use_test_split

    # NEW: Validate data quality
    if HAS_DATA_CONFIG:
        config = DataConfig()
        errors = config.validation.validate_dataframe(self.data)
        if errors:
            print(f"⚠️  Data validation warnings:")
            for error in errors:
                print(f"     • {error}")

    print(f"\n📊 BACKTEST INITIALIZATION")
    print(f"   Companies: {len(self.data):,}")
    print(f"   Using proper train/test split: {use_test_split}")
    if use_test_split and HAS_DATA_CONFIG:
        config = DataConfig()
        test_start, test_end = config.date_splits.get_test_range()
        print(f"   ✓ Data split: TEST [{test_start} to {test_end}] (unseen data)")
    else:
        print(f"   Date range: {datetime.now().date() - timedelta(days=365*lookback_years)} to {datetime.now().date()}")
```

**Why:** 
- Validates data quality automatically
- Shows which split is being used
- Transparent about whether using unseen data (TEST split)

---

### 3. **Add Helper Function** (New function for proper backtest execution)

**NEW:** Add this function before `if __name__ == "__main__":`

```python
def backtest_from_data_source(
    data_path: str = "cache_seed/cleaned_long.parquet",
    market: str = "IN",
    use_test_split: bool = True,
    weight_set: str = "both"
) -> Dict:
    """
    PROPER BACKTEST: Load data, split correctly, then backtest.
    
    This prevents data leakage by:
    1. Loading full historical data
    2. Splitting into TEST [2023-2024] (unseen data)
    3. Backtest ONLY on TEST split
    """
    
    if not HAS_DATA_CONFIG:
        print("❌ ERROR: data_config.py required for proper backtesting")
        return {}

    # Load full data
    try:
        full_data = pd.read_parquet(data_path)
    except FileNotFoundError:
        print(f"❌ Data file not found: {data_path}")
        return {}

    print(f"✓ Loaded {len(full_data):,} records")

    # Split to prevent leakage
    config = DataConfig()

    if use_test_split:
        # Use TEST split (2023-2024) for backtest
        if 'date' in full_data.columns or 'Date' in full_data.columns:
            backtest_data = filter_data_by_split(full_data, "date", split="test")
            test_start, test_end = config.date_splits.get_test_range()
            print(f"✓ Using TEST split: {test_start} to {test_end} ({len(backtest_data):,} records)")
        else:
            backtest_data = full_data
    else:
        backtest_data = full_data

    # Validate
    errors = config.validation.validate_dataframe(backtest_data)
    if errors:
        print(f"⚠️  Data validation warnings: {errors}")

    # Run backtest on proper split
    backtest = WeightBacktester(backtest_data, use_test_split=use_test_split)
    results = backtest.run_backtest(weight_set=weight_set)
    backtest.generate_report(results)

    return results
```

**Why:** Encapsulates the "correct way" to run a backtest. Can be imported and reused.

---

### 4. **Update Main Execution** (Bottom of file)

**BEFORE:**
```python
if __name__ == "__main__":
    print("\n" + "🎯 "*40)
    print("BACKTEST FRAMEWORK - KARZ vs MAIN WEIGHT COMPARISON")
    print("🎯 "*40)
```

**AFTER:**
```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backtest with proper train/test splits"
    )
    parser.add_argument("--market", default="IN")
    parser.add_argument("--data", default="cache_seed/cleaned_long.parquet")
    parser.add_argument("--use-test-split", action="store_true", default=True)
    parser.add_argument("--no-split", action="store_true")
    parser.add_argument("--weight-set", default="both")
    parser.add_argument("--export", help="Export results to CSV")

    args = parser.parse_args()

    print("\n" + "🎯 "*40)
    print("BACKTEST FRAMEWORK - WITH PROPER TRAIN/TEST SPLITS")
    print("🎯 "*40)
    print(f"✓ Using proper train/test splits from data_config.py")
    print(f"✓ Backtest on TEST split: unseen data (2023-2024)")

    # Run with proper splits
    use_split = not args.no_split
    results = backtest_from_data_source(
        data_path=args.data,
        market=args.market,
        use_test_split=use_split,
        weight_set=args.weight_set
    )

    if args.export and results:
        backtest = WeightBacktester(pd.DataFrame(), use_test_split=use_split)
        backtest.export_results(results, args.export)

    print("\n✅ Backtest complete")
```

**Why:** 
- Makes it easy to control split behavior from command line
- Explicit about data being used
- Shows updated behavior clearly

---

## 📋 How to Use the Fixed Script

### Run with proper TEST split (recommended):
```bash
python3 backtest_weight_optimization.py --market IN --weight-set both
```

**Output:**
```
✓ Using proper train/test splits from data_config.py
✓ Backtest on TEST split: unseen data (2023-2024)
📊 BACKTEST INITIALIZATION
   Companies: 1,245
   Using proper train/test split: True
   ✓ Data split: TEST [2023-01-01 to 2024-06-30] (unseen data)

[backtest runs on TEST data only]
```

### Run without split (old behavior, for comparison):
```bash
python3 backtest_weight_optimization.py --market IN --no-split
```

---

## 🔁 Apply This Pattern to Other Scripts

To fix other backtest scripts, apply these 4 changes:

### Change 1: Add imports
```python
try:
    from data_config import DataConfig, filter_data_by_split
    HAS_DATA_CONFIG = True
except ImportError:
    HAS_DATA_CONFIG = False
```

### Change 2: Add data validation in __init__
```python
if HAS_DATA_CONFIG:
    config = DataConfig()
    errors = config.validation.validate_dataframe(self.data)
```

### Change 3: Add a helper function
```python
def run_proper_backtest(data_path, use_test_split=True):
    """Load data, split, then backtest"""
    full_data = pd.read_parquet(data_path)
    config = DataConfig()
    if use_test_split:
        data = filter_data_by_split(full_data, "date", split="test")
    else:
        data = full_data
    return backtest_class(data).run()
```

### Change 4: Update main to use helper
```python
if __name__ == "__main__":
    results = run_proper_backtest(
        data_path="cache_seed/cleaned_long.parquet",
        use_test_split=True
    )
```

---

## ✅ Result

**Before:**
```python
# Backtest uses ALL data (leakage risk)
df = pd.read_parquet("cache_seed/cleaned_long.parquet")
backtest = WeightBacktester(df)
results = backtest.run_backtest()
# ❌ Evaluated on same data used for training
```

**After:**
```python
# Backtest uses only TEST split (no leakage)
results = backtest_from_data_source(
    data_path="cache_seed/cleaned_long.parquet",
    use_test_split=True
)
# ✓ Evaluated on unseen recent data (2023-2024)
```

---

## 📊 Impact

| Aspect | Before | After |
|--------|--------|-------|
| Data used | All historical | TEST split only (2023-2024) |
| Leakage risk | High | None |
| Transparency | Implicit | Explicit (shows which split) |
| Validation | None | Automatic quality checks |
| Fair evaluation | ❌ No | ✅ Yes |

---

## 🎓 Key Concepts

**Data Leakage:** Using future data to predict the past  
**Train/Test Split:** Use old data to build, new data to evaluate  
**TEST Split:** Recent unseen data (2023-2024) for final evaluation  
**Walk-Forward:** Proper way to backtest: train on old, test on new  

---

**Next:** Apply these changes to:
1. backtest_weight_validation.py
2. f1_hyperparameter_tuning.py
3. Any custom backtest scripts you create

Each should take ~15 minutes following this template.
