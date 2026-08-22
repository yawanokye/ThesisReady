from __future__ import annotations

import importlib
import io
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app.data_analysis import (
    data_quality,
    descriptive_statistics,
    recommend_analysis,
    run_mediation,
    run_moderation,
    run_ols,
    run_time_series,
    sem_path_diagram_svg,
)
from app.research_journey import build_journey


def test_quality_and_descriptives_are_calculated_from_raw_data():
    df = pd.DataFrame({"x": [1,2,3,4,5,6,7,8,9,100], "group": ["a","a","a","a","b","b","b","b","b","b"]})
    q = data_quality(df)
    d = descriptive_statistics(df)
    assert q["rows"] == 10
    assert q["numeric_outliers"][0]["iqr_outliers"] >= 1
    assert d["numeric"][0]["mean"] == 14.5
    assert d["categorical"][0]["levels"][0]["value"] == "b"


def test_ols_returns_real_coefficients_and_diagnostics():
    rng = np.random.default_rng(42)
    x = rng.normal(size=180)
    z = rng.normal(size=180)
    y = 1.5 + 2.2 * x - 0.7 * z + rng.normal(scale=.25, size=180)
    result = run_ols(pd.DataFrame({"x": x, "z": z, "y": y}), "y", ["x", "z"], robust=True)
    params = {r["term"]: r for r in result["parameters"]}
    assert abs(params["x"]["coefficient"] - 2.2) < .1
    assert params["x"]["pvalue"] < .001
    assert "vif" in result["diagnostics"]


def test_mediation_and_moderation_use_uploaded_values():
    rng = np.random.default_rng(7)
    x = rng.normal(size=240)
    w = rng.normal(size=240)
    m = .8*x + .15*w + rng.normal(scale=.4,size=240)
    y = .3*x + .7*m + .45*x*w + rng.normal(scale=.5,size=240)
    df = pd.DataFrame({"x":x,"w":w,"m":m,"y":y})
    med = run_mediation(df,"x","m","y",bootstrap=250)
    mod = run_moderation(df,"x","w","y")
    assert med["effects"]["indirect"] > 0
    assert len(med["effects"]) >= 6
    assert any(r["term"] == "interaction" for r in mod["parameters"])


def test_time_series_includes_stationarity_and_model_fit():
    rng=np.random.default_rng(4)
    n=80
    dates=pd.date_range("2019-01-01",periods=n,freq="M")
    y=np.zeros(n)
    for i in range(1,n): y[i]=.55*y[i-1]+rng.normal(scale=.6)
    df=pd.DataFrame({"date":dates,"y":y})
    result=run_time_series(df,"y","date","arima",[1,0,0])
    assert result["model_type"] == "arima"
    assert "adf" in result["stationarity"]
    assert result["model"]["aic"] is not None


def test_sem_diagram_is_self_contained_professional_svg():
    svg=sem_path_diagram_svg([
        {"from":"Teacher Leadership","to":"Self-Efficacy","std_estimate":.51,"pvalue":.001},
        {"from":"Self-Efficacy","to":"Instructional Practice","std_estimate":.44,"pvalue":.004},
    ])
    assert svg.startswith("<svg")
    assert "marker-end='url(#arrow)'" in svg
    assert "Teacher Leadership" in svg
    assert "0.510" in svg


def test_analysis_recommendations_use_objectives_and_optional_framework():
    recs=recommend_analysis({},["To determine whether self-efficacy mediates the relationship between leadership and practice"],"")
    assert recs[0]["type"] == "mediation"
    recs2=recommend_analysis({},["To forecast quarterly revenue using historical observations"],"")
    assert any(r["type"] == "time_series" for r in recs2)


def test_conceptual_framework_is_optional_and_analysis_stage_links_to_workspace():
    project={"title":"Study","drafts":{},"profile":{"research_area":"Management","study_context":"A sufficiently detailed Ghanaian context for the study.","research_approach":"Quantitative","objectives":["Examine X and Y"],"research_questions":["What is the relationship between X and Y?"],"variables":["X","Y"],"hypotheses":["X is related to Y"],"research_design":"Cross-sectional","population":"Staff","sample_size":"200","sampling_strategy":"Random","instruments":"Questionnaire","ethics":"Approval pending","analysis_plan":"OLS"}}
    journey=build_journey(project)
    theory=next(x for x in journey["stages"] if x["key"]=="theory")
    analysis=next(x for x in journey["stages"] if x["key"]=="analysis")
    assert "conceptual framework/path summary" not in theory["missing"]
    assert analysis["href"] == "/data-analysis"
    assert journey["research_record"]["theory_framework"]["conceptual_framework_optional"] is True


def test_data_analysis_page_and_router_are_exposed():
    root=Path(__file__).resolve().parents[1]
    html=(root/"app/static/data_analysis.html").read_text()
    js=(root/"app/static/data_analysis.js").read_text()
    assert "Data & Analysis Workspace" in html
    assert "Time-series: ARIMA / SARIMAX / VAR" in html
    assert "Panel-data regression" in html
    assert "Structural equation modelling (SEM)" in html
    assert "SEM path analysis diagram" in html
    assert "moderated_mediation" in js
    assert "Download SVG" in html
