from pathlib import Path

import numpy as np
import pandas as pd

from app.advanced_analysis import METHOD_CATALOG, deep_capability, run_anova, run_network, run_svar, run_t_test
from app.data_analysis import consistency_checks, run_panel


def test_catalog_covers_requested_analysis_families_and_guidance():
    required = {
        "t_test", "anova", "ancova", "manova", "clrm", "quantile_regression", "dols", "ardl", "nardl",
        "decomposition", "time_series", "cointegration", "vecm", "svar", "tvp_var", "volatility", "network",
        "wavelet", "emd", "ml_forecasting", "deep_forecasting", "foundation_forecasting", "hybrid_forecasting",
        "panel", "sem", "mediation", "moderation", "moderated_mediation", "multilevel", "logistic", "ordinal",
        "multinomial", "count_glm", "reliability", "hierarchical",
    }
    assert required.issubset(METHOD_CATALOG)
    for key in required:
        item = METHOD_CATALOG[key]
        assert item.get("variants"), key
        assert item.get("assumptions"), key
        assert item.get("diagnostics"), key


def test_t_test_and_anova_are_computed_from_data():
    rng = np.random.default_rng(42)
    n = 120
    g = np.where(np.arange(n) % 2 == 0, "A", "B")
    y = rng.normal(size=n) + (g == "B") * 0.7
    df = pd.DataFrame({"y": y, "g": g})
    t = run_t_test(df, "y", "independent_welch", "g", "A", "B")
    a = run_anova(df, "y", "g")
    assert t["analysis"] == "t_test"
    assert t["test"]["pvalue"] is not None
    assert "levene" in t["diagnostics"]
    assert a["analysis"] == "anova"
    assert a["effect_size"]["eta_squared"] is not None
    assert "normality_by_group" in a["diagnostics"]


def test_panel_variants_and_panel_structure_diagnostics():
    rng = np.random.default_rng(7)
    rows = []
    for entity in range(12):
        unit = rng.normal()
        for time in range(6):
            x = rng.normal()
            rows.append((entity, time, x, 1 + unit + 0.8 * x + 0.05 * time + rng.normal(scale=0.4)))
    df = pd.DataFrame(rows, columns=["entity", "time", "x", "y"])
    for estimator in ["pooled_ols", "fixed_effects", "time_fixed_effects", "two_way_fixed_effects", "random_effects"]:
        result = run_panel(df, "y", ["x"], "entity", "time", estimator)
        assert result["analysis"] == "panel_regression"
        assert result["entities"] == 12
        assert result["periods"] == 6
        assert result["diagnostics"]["balanced_panel"] is True


def test_recursive_svar_is_structurally_identified_without_inventing_ab_matrices():
    rng = np.random.default_rng(11)
    n = 110
    values = np.zeros((n, 2))
    eps = rng.normal(size=(n, 2))
    A = np.array([[0.45, 0.10], [-0.08, 0.35]])
    for i in range(1, n):
        values[i] = A @ values[i - 1] + eps[i]
    df = pd.DataFrame({"date": pd.date_range("2010-01-01", periods=n, freq="MS"), "a": values[:, 0], "b": values[:, 1]})
    result = run_svar(df, ["a", "b"], "date", 1, "recursive")
    assert result["model_type"] == "recursive_cholesky"
    assert result["diagnostics"]["stable"] in {True, False}
    assert "recursive Cholesky" in result["diagnostics"]["identification"]
    assert result["impulse_responses"]


def test_network_analysis_has_metrics_and_professional_svg():
    df = pd.DataFrame({"source": ["A", "A", "B", "C", "D"], "target": ["B", "C", "C", "D", "A"], "weight": [1, 2, 1, 3, 1]})
    result = run_network(df, "source", "target", "weight", False)
    assert result["network"]["nodes"] == 4
    assert result["centrality"]
    assert result["diagram_svg"].startswith("<svg")
    assert "ProjectReady network analysis" in result["diagram_svg"]


def test_unavailable_foundation_runtime_fails_closed_instead_of_substitution():
    result = deep_capability("timesfm")
    assert result["model_type"] == "timesfm"
    assert "substitute" in result["message"].lower() or result["runtime_available"] is True


def test_consistency_warning_for_student_t_with_unequal_variance():
    result = {"analysis": "t_test", "variant": "independent_student", "diagnostics": {"levene": {"pvalue": 0.001}}}
    checks = consistency_checks(result)
    assert any("Welch" in x["message"] for x in checks)


def test_analysis_ui_lists_requested_advanced_families_and_assumptions_panel():
    root = Path(__file__).resolve().parents[1]
    html = (root / "app/static/data_analysis.html").read_text(encoding="utf-8")
    js = (root / "app/static/data_analysis.js").read_text(encoding="utf-8")
    for text in ["t_test", "anova", "ancova", "manova", "dols", "ardl", "nardl", "vecm", "svar", "tvp_var", "dcc_garch", "network", "wavelet", "emd", "foundation_forecasting"]:
        assert f'value="{text}"' in html
    for text in ["PatchTST", "Informer", "Autoformer", "N-BEATS", "N-HiTS", "DeepAR", "TimesFM", "Chronos", "TimeGPT", "XGBoost", "LightGBM", "CatBoost"]:
        assert text in js
    assert "Assumptions and diagnostics" in js
    assert "professional" in html.lower()
