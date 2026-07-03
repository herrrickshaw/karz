"""
Repository Data Usage Analyzer
==============================

Analyzes:
1. Which Python scripts use which data sources
2. Whether data is being used for testing only vs training+validation
3. Data split consistency across the project
4. Exhaustive vs sample data testing
5. Missing validations and gaps

Usage:
    analyzer = RepositoryDataAnalyzer("/path/to/repo")
    analysis = analyzer.analyze_all()
    analysis.print_report()
"""

import ast
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime
import json


@dataclass
class ScriptAnalysis:
    """Analysis of a single Python script."""
    file_path: str
    script_name: str

    # Data usage
    loaded_data_sources: List[str] = field(default_factory=list)
    created_data_sources: List[str] = field(default_factory=list)
    data_transformations: List[str] = field(default_factory=list)

    # Data splitting
    has_train_test_split: bool = False
    split_method: Optional[str] = None  # "chronological", "random", "none"
    uses_all_data: bool = False
    trains_on_test_data: bool = False
    backtest_dates: Optional[Tuple[str, str]] = None

    # Testing approach
    is_exhaustive: bool = False  # Tests on all data
    uses_samples: bool = False   # Tests on subset
    sample_size: Optional[int] = None

    # Issues found
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class RepositoryAnalysisReport:
    """Complete repository analysis."""
    generated_at: str
    total_scripts: int
    scripts_analyzed: List[ScriptAnalysis] = field(default_factory=list)

    # Summary stats
    scripts_with_issues: int = 0
    scripts_missing_train_val_split: int = 0
    scripts_training_on_test: int = 0
    exhaustive_vs_sample_breakdown: Dict[str, int] = field(default_factory=dict)

    # Data lineage
    data_dependency_graph: Dict[str, List[str]] = field(default_factory=dict)
    source_to_users: Dict[str, List[str]] = field(default_factory=dict)

    # Recommendations
    recommendations: List[str] = field(default_factory=list)

    def save_report(self, path: str):
        """Save report as JSON."""
        data = asdict(self)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def print_report(self):
        """Print human-readable report."""
        print("\n" + "="*70)
        print("REPOSITORY DATA USAGE ANALYSIS REPORT")
        print("="*70)
        print(f"Generated: {self.generated_at}")
        print(f"\n📊 SUMMARY:")
        print(f"  Total scripts analyzed: {self.total_scripts}")
        print(f"  Scripts with issues: {self.scripts_with_issues}")
        print(f"  Missing train/val splits: {self.scripts_missing_train_val_split}")
        print(f"  Training on test data: {self.scripts_training_on_test}")

        print(f"\n🔄 DATA TESTING APPROACH:")
        for approach, count in self.exhaustive_vs_sample_breakdown.items():
            print(f"  {approach}: {count} scripts")

        print(f"\n📋 SCRIPTS NEEDING ATTENTION:")
        for script in self.scripts_analyzed:
            if script.issues or script.trains_on_test_data:
                print(f"\n  {script.script_name}")
                if script.issues:
                    for issue in script.issues:
                        print(f"    ❌ {issue}")
                if script.warnings:
                    for warn in script.warnings:
                        print(f"    ⚠️  {warn}")

        print(f"\n💡 RECOMMENDATIONS:")
        for i, rec in enumerate(self.recommendations[:5], 1):
            print(f"  {i}. {rec}")


class RepositoryDataAnalyzer:
    """Main analyzer coordinator."""

    def __init__(self, base_path: str = "/Users/umashankar/Downloads/code/python_files"):
        self.base_path = Path(base_path)
        self.scripts = []
        self.report = None

    def analyze_all(self) -> RepositoryAnalysisReport:
        """Run complete repository analysis."""
        print("🔍 Analyzing repository data usage patterns...")

        # Find all Python scripts
        print("\n[1/3] Discovering Python scripts...")
        py_scripts = self._discover_scripts()
        print(f"  ✓ Found {len(py_scripts)} scripts")

        # Analyze each script
        print("\n[2/3] Analyzing individual scripts...")
        analyses = []
        for py_file in py_scripts:
            analysis = self._analyze_script(py_file)
            if analysis:
                analyses.append(analysis)
                status = "✓" if not analysis.issues else "⚠️"
                print(f"  {status} {analysis.script_name}")

        # Compile report
        print("\n[3/3] Compiling analysis report...")
        self.report = self._compile_report(analyses)

        return self.report

    def _discover_scripts(self) -> List[Path]:
        """Find all Python scripts in repo."""
        scripts = list(self.base_path.glob("**/*.py"))
        # Filter out common non-analysis scripts
        exclude_patterns = [
            "__pycache__", ".git", ".pytest_cache",
            "site-packages", "venv", "env"
        ]
        filtered = [
            s for s in scripts
            if not any(p in str(s) for p in exclude_patterns)
        ]
        return sorted(filtered)[:100]  # Limit for analysis

    def _analyze_script(self, script_path: Path) -> Optional[ScriptAnalysis]:
        """Analyze a single Python script."""
        try:
            with open(script_path, 'r') as f:
                content = f.read()

            analysis = ScriptAnalysis(
                file_path=str(script_path),
                script_name=script_path.name,
            )

            # Parse AST for imports and function calls
            tree = ast.parse(content)
            self._analyze_ast(tree, analysis, content)

            # Pattern-based analysis for data operations
            self._analyze_patterns(content, analysis)

            # Check for issues
            self._identify_issues(analysis, content)

            return analysis

        except Exception as e:
            print(f"  ✗ Error analyzing {script_path.name}: {e}")
            return None

    def _analyze_ast(self, tree: ast.AST, analysis: ScriptAnalysis, content: str):
        """Analyze Abstract Syntax Tree."""
        for node in ast.walk(tree):
            # Detect data loading
            if isinstance(node, ast.Call):
                func_name = self._get_func_name(node.func)

                if func_name in ['read_parquet', 'read_csv', 'read_excel']:
                    # Extract filename
                    if node.args:
                        filename = self._extract_string_arg(node.args[0])
                        if filename:
                            analysis.loaded_data_sources.append(filename)

                elif func_name == 'train_test_split':
                    analysis.has_train_test_split = True
                    # Infer split method from kwargs
                    for keyword in node.keywords:
                        if keyword.arg == 'test_size':
                            analysis.split_method = 'random'

                elif func_name in ['shuffle', 'sample']:
                    analysis.uses_samples = True

                elif func_name in ['to_parquet', 'to_csv']:
                    if node.args:
                        filename = self._extract_string_arg(node.args[0])
                        if filename:
                            analysis.created_data_sources.append(filename)

    def _analyze_patterns(self, content: str, analysis: ScriptAnalysis):
        """Pattern-based analysis for data operations."""

        # Detect backtest date ranges
        date_pattern = r"(20\d{2}-\d{2}-\d{2}|datetime.*\(.*\d{4}.*\))"
        dates = re.findall(date_pattern, content)
        if len(dates) >= 2:
            analysis.backtest_dates = (dates[0], dates[-1])

        # Detect split methods
        if "loc[:split_point]" in content or ".iloc[:split_idx]" in content:
            analysis.split_method = "chronological"
        elif "train_test_split" in content:
            analysis.split_method = "random"

        # Detect data usage extent
        if re.search(r"\.head\(\d+\)|\.sample\(\)|nrows\s*=|limit\s*=", content):
            analysis.uses_samples = True
            # Try to extract sample size
            match = re.search(r"\.head\((\d+)\)|\.sample\(.*n\s*=\s*(\d+)\)|nrows\s*=\s*(\d+)", content)
            if match:
                for g in match.groups():
                    if g:
                        analysis.sample_size = int(g)
                        break
        else:
            analysis.is_exhaustive = True

        # Detect if training on all data
        if re.search(r"(all_data|full_data|entire_data|\.copy\(\)|X = df|y = df)", content):
            if not analysis.has_train_test_split:
                analysis.uses_all_data = True
                analysis.trains_on_test_data = True

        # Detect transformations
        transformations = []
        if "scale" in content.lower():
            transformations.append("scaling")
        if "normalize" in content.lower():
            transformations.append("normalization")
        if "fillna" in content.lower():
            transformations.append("null_imputation")
        if "drop" in content and ("nan" in content or "null" in content):
            transformations.append("null_removal")
        analysis.data_transformations = transformations

    def _identify_issues(self, analysis: ScriptAnalysis, content: str):
        """Identify data handling issues."""

        # Issue 1: No train/test split
        if not analysis.has_train_test_split and analysis.uses_all_data:
            analysis.issues.append(
                f"Uses all data without train/test split (backtest/analysis on same data)"
            )

        # Issue 2: Sample-based testing instead of exhaustive
        if analysis.uses_samples and not analysis.is_exhaustive:
            analysis.warnings.append(
                f"Testing on samples only ({analysis.sample_size} rows); "
                f"consider exhaustive validation"
            )

        # Issue 3: Random split without seed
        if "test_size" in content and "random_state" not in content:
            analysis.warnings.append(
                "Random train/test split without fixed random_state "
                "(not reproducible)"
            )

        # Issue 4: Date-based backtest without proper split
        if analysis.backtest_dates and not analysis.split_method:
            analysis.warnings.append(
                f"Backtest on date range {analysis.backtest_dates} "
                f"but no explicit train/test split detected"
            )

        # Issue 5: No data validation
        if "assert" not in content and "validate" not in content.lower():
            analysis.warnings.append(
                "No data validation/assertions found; "
                "add checks for data integrity"
            )

        # Issue 6: Multiple data sources without consistency checks
        if len(analysis.loaded_data_sources) > 1:
            if "compare" not in content.lower() and "assert" not in content:
                analysis.warnings.append(
                    f"Uses {len(analysis.loaded_data_sources)} data sources "
                    f"but no consistency checks found"
                )

    def _compile_report(self, analyses: List[ScriptAnalysis]) -> RepositoryAnalysisReport:
        """Compile final report."""

        # Count statistics
        scripts_with_issues = sum(1 for a in analyses if a.issues or a.trains_on_test_data)
        missing_splits = sum(1 for a in analyses if not a.has_train_test_split and a.uses_all_data)
        training_on_test = sum(1 for a in analyses if a.trains_on_test_data)

        exhaustive_count = sum(1 for a in analyses if a.is_exhaustive)
        sample_count = sum(1 for a in analyses if a.uses_samples)

        # Build dependency graph
        data_deps = {}
        source_to_users = {}

        for analysis in analyses:
            if analysis.loaded_data_sources:
                data_deps[analysis.script_name] = analysis.loaded_data_sources

            for source in analysis.created_data_sources:
                if source not in source_to_users:
                    source_to_users[source] = []
                source_to_users[source].append(analysis.script_name)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            analyses, missing_splits, training_on_test
        )

        report = RepositoryAnalysisReport(
            generated_at=datetime.now().isoformat(),
            total_scripts=len(analyses),
            scripts_analyzed=analyses,
            scripts_with_issues=scripts_with_issues,
            scripts_missing_train_val_split=missing_splits,
            scripts_training_on_test=training_on_test,
            exhaustive_vs_sample_breakdown={
                "exhaustive_testing": exhaustive_count,
                "sample_testing": sample_count,
            },
            data_dependency_graph=data_deps,
            source_to_users=source_to_users,
            recommendations=recommendations,
        )

        return report

    def _generate_recommendations(
        self,
        analyses: List[ScriptAnalysis],
        missing_splits: int,
        training_on_test: int,
    ) -> List[str]:
        """Generate actionable recommendations."""

        recommendations = []

        if training_on_test > 0:
            recommendations.append(
                f"🔴 CRITICAL: {training_on_test} scripts train and test on same data. "
                f"Implement chronological train/validation/test split immediately."
            )

        if missing_splits > 0:
            recommendations.append(
                f"⚠️  {missing_splits} scripts lack explicit train/test splits. "
                f"Add date-based splits for backtests (train on older data, test on recent)."
            )

        if any(a.uses_samples for a in analyses):
            sample_scripts = [a.script_name for a in analyses if a.uses_samples][:3]
            recommendations.append(
                f"📊 {len([a for a in analyses if a.uses_samples])} scripts test on samples. "
                f"Examples: {', '.join(sample_scripts)}. "
                f"Add exhaustive validation on ALL data (parquet size is manageable)."
            )

        if any(not a.data_transformations for a in analyses if a.loaded_data_sources):
            recommendations.append(
                "🔧 Many scripts load data but don't document transformations. "
                "Add explicit transformation steps (scaling, normalization, imputation)."
            )

        if any(len(a.loaded_data_sources) > 1 for a in analyses):
            recommendations.append(
                "🔗 Multiple scripts use multiple sources without cross-checking consistency. "
                "Run the DataValidator tool to identify price/date mismatches."
            )

        recommendations.append(
            "📌 Create a data_config.py that defines: (1) train/val/test date ranges, "
            "(2) required data sources, (3) validation rules. All scripts import from it."
        )

        return recommendations

    @staticmethod
    def _get_func_name(func_node) -> Optional[str]:
        """Extract function name from AST node."""
        if isinstance(func_node, ast.Name):
            return func_node.id
        elif isinstance(func_node, ast.Attribute):
            return func_node.attr
        return None

    @staticmethod
    def _extract_string_arg(arg_node) -> Optional[str]:
        """Extract string literal from AST node."""
        if isinstance(arg_node, ast.Constant) and isinstance(arg_node.value, str):
            return arg_node.value
        elif isinstance(arg_node, ast.Str):  # Python 3.7 compat
            return arg_node.s
        return None


# ============================================================================
# DATA SPLIT VALIDATOR
# ============================================================================

class DataSplitValidator:
    """Validate train/val/test splits."""

    @staticmethod
    def validate_chronological_split(
        df: 'pd.DataFrame',
        date_col: str,
        train_ratio: float = 0.6,
        val_ratio: float = 0.2,
        test_ratio: float = 0.2,
    ) -> Dict[str, Tuple[datetime, datetime]]:
        """Validate chronological train/val/test split."""
        import pandas as pd

        df_sorted = df.sort_values(date_col)
        n = len(df_sorted)

        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        splits = {
            "train": (
                df_sorted.iloc[0][date_col],
                df_sorted.iloc[train_end-1][date_col]
            ),
            "validation": (
                df_sorted.iloc[train_end][date_col],
                df_sorted.iloc[val_end-1][date_col]
            ),
            "test": (
                df_sorted.iloc[val_end][date_col],
                df_sorted.iloc[-1][date_col]
            ),
        }

        return splits

    @staticmethod
    def check_data_leakage(
        train_dates: Tuple[str, str],
        val_dates: Tuple[str, str],
        test_dates: Tuple[str, str],
    ) -> bool:
        """Check for date overlap (leakage) between splits."""
        import pandas as pd

        train_max = pd.to_datetime(train_dates[1])
        val_min = pd.to_datetime(val_dates[0])
        val_max = pd.to_datetime(val_dates[1])
        test_min = pd.to_datetime(test_dates[0])

        # Ensure no overlap
        if train_max >= val_min:
            return True  # Leakage detected
        if val_max >= test_min:
            return True  # Leakage detected

        return False  # No leakage


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    analyzer = RepositoryDataAnalyzer()
    report = analyzer.analyze_all()
    report.print_report()
    report.save_report("/tmp/repo_data_analysis.json")
