from __future__ import annotations

import ast

import repo_data_analyzer as rda


def test_extract_string_arg_handles_non_literals():
    # ast.Str was removed in Python 3.14; a variable argument used to raise AttributeError there.
    call = ast.parse("pd.read_csv(path)").body[0].value
    assert rda.RepositoryDataAnalyzer._extract_string_arg(call.args[0]) is None
    lit = ast.parse("pd.read_csv('a.csv')").body[0].value
    assert rda.RepositoryDataAnalyzer._extract_string_arg(lit.args[0]) == "a.csv"


def test_script_with_variable_path_is_analysed(tmp_path):
    (tmp_path / "s.py").write_text("import pandas as pd\np = 'x.csv'\ndf = pd.read_csv(p)\nassert df is not None\n")
    report = rda.RepositoryDataAnalyzer(str(tmp_path)).analyze_all()
    assert report.total_scripts == 1
