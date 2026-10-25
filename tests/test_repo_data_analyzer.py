"""Tests for repo_data_analyzer.py static analysis and split validation."""
import pandas as pd
import pytest

from repo_data_analyzer import DataSplitValidator, RepositoryDataAnalyzer


def analyse(tmp_path, src):
    p = tmp_path / "s.py"
    p.write_text(src)
    return RepositoryDataAnalyzer(str(tmp_path))._analyze_script(p)


def test_detects_loaded_and_created_sources(tmp_path):
    a = analyse(tmp_path, "import pandas as pd\ndf = pd.read_parquet('a.parquet')\n"
                          "df.to_csv('out.csv')\nassert len(df)\n")
    assert a.loaded_data_sources == ["a.parquet"]
    assert a.created_data_sources == ["out.csv"]


def test_non_literal_path_argument_does_not_abort_the_analysis(tmp_path):
    # `ast.Str` no longer exists on Python 3.12+; a variable path must not
    # make the whole script unanalysable.
    a = analyse(tmp_path, "import pandas as pd\npath = 'x.csv'\ndf = pd.read_csv(path)\n")
    assert a is not None
    assert a.loaded_data_sources == []


def test_random_split_without_seed_warned(tmp_path):
    a = analyse(tmp_path, "from sklearn.model_selection import train_test_split\n"
                          "a, b = train_test_split(X, test_size=0.2)\n")
    assert a.has_train_test_split and a.split_method == "random"
    assert any("random_state" in w for w in a.warnings)


def test_discover_scripts_excludes_venv_and_caches(tmp_path):
    for d in ("venv", "__pycache__", "pkg"):
        (tmp_path / d).mkdir()
        (tmp_path / d / "m.py").write_text("x = 1\n")
    found = RepositoryDataAnalyzer(str(tmp_path))._discover_scripts()
    assert [p.parent.name for p in found] == ["pkg"]


def test_chronological_split_boundaries():
    df = pd.DataFrame({"d": pd.date_range("2024-01-01", periods=10)}).sample(frac=1, random_state=0)
    s = DataSplitValidator.validate_chronological_split(df, "d")
    assert s["train"] == (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-06"))
    assert s["validation"] == (pd.Timestamp("2024-01-07"), pd.Timestamp("2024-01-08"))
    assert s["test"] == (pd.Timestamp("2024-01-09"), pd.Timestamp("2024-01-10"))


@pytest.mark.parametrize("train,val,test,leak", [
    (("2015-01-01", "2021-12-31"), ("2022-01-01", "2022-12-31"), ("2023-01-01", "2024-06-30"), False),
    (("2015-01-01", "2022-01-01"), ("2022-01-01", "2022-12-31"), ("2023-01-01", "2024-06-30"), True),
    (("2015-01-01", "2021-12-31"), ("2022-01-01", "2023-01-01"), ("2023-01-01", "2024-06-30"), True),
])
def test_check_data_leakage(train, val, test, leak):
    assert DataSplitValidator.check_data_leakage(train, val, test) is leak
