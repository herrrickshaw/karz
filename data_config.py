"""
Data Configuration & Registry
=============================

Single source of truth for:
1. Train/validation/test date ranges
2. Required data sources
3. Data validation rules
4. Universe definitions (symbols to analyze)
5. Data freshness requirements
6. Cross-source consistency rules

All analysis scripts should import from this module and use these definitions.

Usage:
    from data_config import DataConfig, filter_data_by_split

    config = DataConfig()
    train_start, train_end = config.date_splits.get_train_range()
    test_df = filter_data_by_split(df, "date", split="test")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd

# Share of rows that may be "extreme moves" before validate_dataframe reports them.
EXTREME_MOVE_ROW_SHARE = 0.01
# Tolerance (absolute) when comparing two values where one of them is zero.
ZERO_VALUE_TOLERANCE = 0.01
# Symbol coverage required by validate_universe_consistency.
MIN_SYMBOL_COVERAGE = 0.8


# ============================================================================
# GLOBAL DATE SPLITS (EXHAUSTIVE VALIDATION)
# ============================================================================

@dataclass
class DateSplits:
    """Define train/validation/test date ranges for exhaustive validation."""

    # CRITICAL: All historical data is split chronologically
    # Earlier data trains, middle data validates, recent data tests
    TRAIN_START = "2015-01-01"      # Oldest available data
    TRAIN_END = "2021-12-31"        # 7 years of training data
    VAL_START = "2022-01-01"        # Validation period
    VAL_END = "2022-12-31"          # 1 year validation
    TEST_START = "2023-01-01"       # Recent unseen data
    TEST_END = "2024-06-30"         # Current date (always update)

    @classmethod
    def get_train_range(cls) -> Tuple[str, str]:
        """Returns train date range."""
        return (cls.TRAIN_START, cls.TRAIN_END)

    @classmethod
    def get_validation_range(cls) -> Tuple[str, str]:
        """Returns validation date range."""
        return (cls.VAL_START, cls.VAL_END)

    @classmethod
    def get_test_range(cls) -> Tuple[str, str]:
        """Returns test date range."""
        return (cls.TEST_START, cls.TEST_END)

    @classmethod
    def validate_no_overlap(cls) -> bool:
        """Ensure splits don't overlap."""
        assert cls.TRAIN_END < cls.VAL_START, "Train-Val overlap!"
        assert cls.VAL_END < cls.TEST_START, "Val-Test overlap!"
        return True


# ============================================================================
# DATA SOURCES REGISTRY
# ============================================================================

@dataclass
class DataSourceRegistry:
    """Registry of all data sources used in the project."""

    # India market
    INDIA_PRIMARY = {
        "name": "cleaned_long.parquet",
        "path": "cache_seed/cleaned_long.parquet",
        "source_type": "parquet",
        "coverage": "NSE + BSE",
        "record_count": 15_000_000,  # Approximate
        "symbols": 2681,
        "date_range": ("2015-01-01", "2024-06-30"),
        "freshness_required_days": 1,
    }

    # Global markets
    GLOBAL_SOURCES = {
        "US": {
            "name": "cleaned_long_US.parquet",
            "path": "cache_seed/cleaned_long_US.parquet",
            "coverage": "US (10K+ stocks)",
            "symbols": 10433,
        },
        "CN": {
            "name": "cleaned_long_CN.parquet",
            "path": "cache_seed/cleaned_long_CN.parquet",
            "coverage": "China A-shares",
            "symbols": 5534,
        },
        "JP": {
            "name": "cleaned_long_JP.parquet",
            "path": "cache_seed/cleaned_long_JP.parquet",
            "coverage": "Japan (JPX)",
            "symbols": 3084,
        },
        "KR": {
            "name": "cleaned_long_KR.parquet",
            "path": "cache_seed/cleaned_long_KR.parquet",
            "coverage": "Korea (KOSPI/KOSDAQ)",
            "symbols": 2606,
        },
        "AU": {
            "name": "cleaned_long_AU.parquet",
            "path": "cache_seed/cleaned_long_AU.parquet",
            "coverage": "Australia (ASX)",
            "symbols": 2000,
        },
        "EU": {
            "name": "cleaned_long_EU.parquet",
            "path": "cache_seed/cleaned_long_EU.parquet",
            "coverage": "Europe (Large-caps)",
            "symbols": 500,
        },
    }

    # Fundamentals and reference data
    FUNDAMENTALS = {
        "path": "cache_seed/fundamentals/",
        "contents": ["balance_sheet", "income_statement", "cash_flow"],
        "source": "yfinance / SEC EDGAR",
    }

    # Screening results
    DISCOVERED_SCREENS = {
        "path": "cache_seed/discovered_screens/",
        "description": "Pre-computed screener results",
    }

    @classmethod
    def get_source(cls, market: str) -> Dict | None:
        """Get source config for a market (None for an unknown market code)."""
        if market == "IN":
            return cls.INDIA_PRIMARY
        return cls.GLOBAL_SOURCES.get(market)

    @classmethod
    def get_all_markets(cls) -> List[str]:
        """Get list of all available markets."""
        return ["IN"] + list(cls.GLOBAL_SOURCES.keys())


# ============================================================================
# DATA VALIDATION RULES
# ============================================================================

@dataclass
class DataValidationRules:
    """Define data quality requirements."""

    # Null handling
    MAX_NULL_PCT = 0.05  # Allow max 5% nulls per column
    CRITICAL_COLUMNS = ["open", "high", "low", "close", "volume", "date"]

    # OHLC sanity
    HIGH_MUST_BE_MAX = True         # high >= max(o,h,l,c)
    LOW_MUST_BE_MIN = True          # low <= min(o,h,l,c)
    CLOSE_MUST_BE_NUMERIC = True
    VOLUME_MUST_BE_POSITIVE = True

    # Price movement
    MAX_DAILY_MOVE_PCT = 50  # Flag if >50% move (penny stocks anomaly)
    MIN_PRICE = 0.01

    # Date continuity
    MAX_GAP_DAYS = 5  # Alert if gap > 5 days
    REQUIRE_TRADING_DAYS_ONLY = True

    # Time series
    MIN_RECORDS_PER_SYMBOL = 252  # At least 1 trading year
    MIN_SYMBOLS_IN_MARKET = 100   # Market must have minimum coverage

    @staticmethod
    def validate_dataframe(df: pd.DataFrame, raise_on_error: bool = False) -> List[str]:
        """Run all validation rules on an OHLCV DataFrame and return the error messages.

        Note: as a side effect a ``returns`` column (close pct-change) is added to ``df``
        when it has a ``close`` column; callers that must not be mutated should pass a copy.
        """
        errors: List[str] = []

        # Check critical columns exist
        for col in DataValidationRules.CRITICAL_COLUMNS:
            if col not in df.columns:
                msg = f"Missing critical column: {col}"
                errors.append(msg)
                if raise_on_error:
                    raise ValueError(msg)

        # Check nulls
        for col in df.columns:
            null_pct = df[col].isnull().sum() / len(df)
            if null_pct > DataValidationRules.MAX_NULL_PCT:
                msg = f"Column {col} has {null_pct:.1%} nulls (max: {DataValidationRules.MAX_NULL_PCT:.1%})"
                errors.append(msg)

        # Check OHLC sanity
        if all(c in df.columns for c in ['open', 'high', 'low', 'close']):
            invalid = (df['high'] < df['low']).sum()
            if invalid > 0:
                msg = f"{invalid} rows with high < low"
                errors.append(msg)

        # Check price movement sanity
        if 'close' in df.columns:
            df['returns'] = df['close'].pct_change()
            extreme = (df['returns'].abs() > DataValidationRules.MAX_DAILY_MOVE_PCT).sum()
            if extreme > len(df) * EXTREME_MOVE_ROW_SHARE:
                msg = f"{extreme} extreme daily moves (>{DataValidationRules.MAX_DAILY_MOVE_PCT}%)"
                errors.append(msg)

        return errors


# ============================================================================
# UNIVERSE DEFINITIONS (what to analyze)
# ============================================================================

@dataclass
class Universe:
    """Define which symbols/markets to analyze."""

    INDIA_FOCUS = {
        "market": "IN",
        "min_market_cap_usd": 100_000_000,  # >$100M
        "min_volume_usd": 1_000_000,        # >$1M daily avg
        "lookback_years": 2,
        "symbols": ["RELIANCE", "TCS", "INFY", "ICICIBANK", "SBIN", "MARUTI",
                    "BAJAJFINSV", "BHARTIARTL", "HINDUNILVR", "WIPRO"],  # Top 10
    }

    US_LARGE_CAP = {
        "market": "US",
        "min_market_cap_usd": 10_000_000_000,  # >$10B
        "min_volume_usd": 10_000_000,          # >$10M daily avg
        "lookback_years": 3,
        "symbols": None,  # Use all S&P 500
        "count_limit": 500,
    }

    GLOBAL_ALL = {
        "markets": ["US", "CN", "JP", "KR", "AU", "EU"],
        "min_market_cap_usd": 50_000_000,
        "min_volume_usd": 500_000,
        "lookback_years": 2,
        "exhaustive": True,
    }

    @classmethod
    def get_universe(cls, preset: str = "india_focus") -> Dict:
        """Get universe by preset."""
        presets = {
            "india_focus": cls.INDIA_FOCUS,
            "us_large_cap": cls.US_LARGE_CAP,
            "global_all": cls.GLOBAL_ALL,
        }
        return presets.get(preset, cls.INDIA_FOCUS)


# ============================================================================
# DATA FRESHNESS REQUIREMENTS
# ============================================================================

@dataclass
class FreshnessRequirements:
    """Define how fresh data must be for different use cases."""

    # Real-time screener
    INTRADAY_SCREENER = {
        "purpose": "Intraday alerts & screener",
        "max_age_minutes": 15,
        "required_sources": ["live_ticker"],
    }

    # Daily backtest
    DAILY_SCREENER = {
        "purpose": "Daily opening signals",
        "max_age_hours": 24,
        "required_sources": ["cleaned_long.parquet"],
    }

    # Weekly analysis
    WEEKLY_ANALYSIS = {
        "purpose": "Weekly/monthly portfolio reviews",
        "max_age_days": 7,
        "required_sources": ["cleaned_long.parquet", "fundamentals"],
    }

    # Historical backtest (can be stale)
    BACKTEST_HISTORICAL = {
        "purpose": "Historical backtest & research",
        "max_age_days": 365,
        "required_sources": ["cleaned_long.parquet"],
        "note": "Can be months stale; not for live trading",
    }

    # (requirement key, seconds per unit, label, number format) in precedence order.
    _TIMED_LIMITS = (
        ("max_age_minutes", 60.0, "min", ".0f"),
        ("max_age_hours", 3600.0, "hours", ".1f"),
    )

    @staticmethod
    def check_freshness(
        source_last_updated: datetime,
        requirement: Dict
    ) -> Tuple[bool, str]:
        """Return (is_fresh, message) for a source last updated at ``source_last_updated``.

        ``requirement`` is one of the preset dicts above (keys ``max_age_minutes``,
        ``max_age_hours`` or ``max_age_days``); anything else is treated as fresh.
        """
        age_delta = datetime.now() - source_last_updated

        for key, seconds_per_unit, label, fmt in FreshnessRequirements._TIMED_LIMITS:
            if key in requirement:
                age = age_delta.total_seconds() / seconds_per_unit
                max_age = requirement[key]
                return age <= max_age, f"Age: {age:{fmt}} {label} (max: {max_age} {label})"

        if "max_age_days" in requirement:
            age = age_delta.days
            max_age = requirement["max_age_days"]
            return age <= max_age, f"Age: {age} days (max: {max_age} days)"

        return True, "Unknown freshness requirement"


# ============================================================================
# CROSS-SOURCE CONSISTENCY RULES
# ============================================================================

@dataclass
class ConsistencyRules:
    """Define acceptable discrepancies between sources."""

    # Price discrepancy tolerance
    PRICE_DISCREPANCY_PCT = 2.0  # Allow 2% difference (bid-ask, timing)
    VOLUME_DISCREPANCY_PCT = 5.0  # Allow 5% (different reporting)

    # Date range compatibility
    MIN_OVERLAP_PCTS = 80  # Must have 80% date overlap

    # Symbol name matching
    ALLOW_SYMBOL_ALIASES = True
    SYMBOL_MAPPINGS = {
        # Bhavcopy -> yfinance mappings
        "SBIN": "SBIN.NS",
        "TCS": "TCS.NS",
        "INFY": "INFY.NS",
    }

    @staticmethod
    def acceptable_difference(
        value1: float,
        value2: float,
        tolerance_pct: float
    ) -> bool:
        """Check if difference is acceptable."""
        if value1 == 0 or value2 == 0:
            return abs(value1 - value2) < ZERO_VALUE_TOLERANCE

        pct_diff = abs(value1 - value2) / max(abs(value1), abs(value2))
        return pct_diff <= (tolerance_pct / 100)


# ============================================================================
# CONFIGURATION SINGLETON
# ============================================================================

class DataConfig:
    """Main configuration object."""

    def __init__(self):
        self.date_splits = DateSplits()
        self.sources = DataSourceRegistry()
        self.validation = DataValidationRules()
        self.universe = Universe()
        self.freshness = FreshnessRequirements()
        self.consistency = ConsistencyRules()

    def get_split_for_purpose(self, purpose: str) -> Tuple[str, str]:
        """Get appropriate date split for analysis purpose (unknown purposes use the test split)."""
        ranges = {
            "backtest": self.date_splits.get_test_range,
            "validation": self.date_splits.get_validation_range,
            "training": self.date_splits.get_train_range,
        }
        return ranges.get(purpose, self.date_splits.get_test_range)()


# ============================================================================
# HELPERS
# ============================================================================

def filter_data_by_split(
    df: pd.DataFrame,
    date_col: str,
    split: str = "test"
) -> pd.DataFrame:
    """Return the rows of ``df`` whose ``date_col`` falls in the train/validation/test range.

    Note: ``df[date_col]`` is converted to datetime in place (the caller's frame is mutated).
    """
    ranges = {
        "train": DateSplits.get_train_range,
        "validation": DateSplits.get_validation_range,
        "test": DateSplits.get_test_range,
    }
    if split not in ranges:
        raise ValueError(f"Unknown split: {split}")
    start, end = ranges[split]()

    df[date_col] = pd.to_datetime(df[date_col])
    return df[(df[date_col] >= start) & (df[date_col] <= end)]


def validate_universe_consistency(
    universe_dict: Dict,
    df: pd.DataFrame
) -> List[str]:
    """Check that ``df['symbol']`` covers the universe's symbol list; returns issue messages."""
    issues: List[str] = []

    # Check symbol count
    if "symbols" in universe_dict and isinstance(universe_dict["symbols"], list):
        available = set(universe_dict["symbols"]) & set(df['symbol'].unique())
        if len(available) < len(universe_dict["symbols"]) * MIN_SYMBOL_COVERAGE:
            issues.append(f"Only {len(available)}/{len(universe_dict['symbols'])} "
                         f"defined symbols found in data")

    # Market-cap filtering would need fundamentals data and is not checked here.

    return issues


# ============================================================================
# MAIN EXECUTION (Config Validation)
# ============================================================================

if __name__ == "__main__":
    print("🔍 Validating Data Configuration...")
    print()

    # Validate date splits
    config = DataConfig()
    config.date_splits.validate_no_overlap()
    print("✓ Date splits are non-overlapping")

    # Print registry
    print("\n📊 Data Sources Registry:")
    print(f"  India Primary: {config.sources.INDIA_PRIMARY['name']}")
    for market, source in config.sources.GLOBAL_SOURCES.items():
        print(f"  {market}: {source['name']}")

    # Print validation rules
    print("\n✅ Data Validation Rules:")
    print(f"  Max null %: {config.validation.MAX_NULL_PCT:.1%}")
    print(f"  Min records per symbol: {config.validation.MIN_RECORDS_PER_SYMBOL}")
    print(f"  Max daily move flag: {config.validation.MAX_DAILY_MOVE_PCT}%")

    # Print universe
    print("\n🌍 Universe Definitions:")
    for preset in ["india_focus", "us_large_cap", "global_all"]:
        univ = config.universe.get_universe(preset)
        print(f"  {preset}: {univ}")

    print("\n✓ Configuration validated successfully")
