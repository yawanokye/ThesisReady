from __future__ import annotations

import base64
import gzip
import io
import json
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any

from app.database import get_conn

from app.advanced_analysis import (
    METHOD_CATALOG,
    deep_capability,
    run_advanced_forecasting_adapter,
    method_catalog,
    run_ancova,
    run_anova,
    run_ardl,
    run_cointegration,
    run_dcc_garch,
    run_decomposition,
    run_dols,
    run_emd,
    run_manova,
    run_ml_forecast,
    run_nardl,
    run_network,
    run_quantile,
    run_svar,
    run_t_test,
    run_tvp_var,
    run_vecm,
    run_volatility,
    run_wavelet,
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_ROWS = 200_000
MAX_COLUMNS = 300


def init_analysis_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_datasets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                file_type TEXT NOT NULL,
                content_b64 TEXT NOT NULL,
                schema_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_datasets_project ON analysis_datasets(project_id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_runs (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                analysis_type TEXT NOT NULL,
                specification_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES analysis_datasets(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analysis_runs_project ON analysis_runs(project_id)")
        conn.commit()


def _compress(content: bytes) -> str:
    return base64.b64encode(gzip.compress(content, compresslevel=6)).decode("ascii")


def _decompress(text: str) -> bytes:
    return gzip.decompress(base64.b64decode(text.encode("ascii")))


def _load_dataframe(filename: str, content: bytes):
    try:
        import pandas as pd
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("Data analysis requires pandas. Install the analysis dependencies and redeploy.") from exc
    suffix = str(filename or "").lower().rsplit(".", 1)[-1] if "." in str(filename or "") else ""
    if suffix == "csv":
        df = pd.read_csv(io.BytesIO(content))
    elif suffix in {"xlsx", "xlsm", "xls"}:
        df = pd.read_excel(io.BytesIO(content), engine="openpyxl" if suffix != "xls" else None)
    elif suffix == "tsv":
        df = pd.read_csv(io.BytesIO(content), sep="\t")
    else:
        raise ValueError("Raw analysis data must be CSV, TSV, XLSX or XLSM.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"Dataset has {len(df):,} rows. The current workspace limit is {MAX_ROWS:,} rows per analysis dataset.")
    if len(df.columns) > MAX_COLUMNS:
        raise ValueError(f"Dataset has {len(df.columns)} columns. The current workspace limit is {MAX_COLUMNS} columns.")
    df.columns = [str(c).strip() or f"column_{i+1}" for i, c in enumerate(df.columns)]
    return df


def _dtype_label(series) -> str:
    import pandas as pd
    if pd.api.types.is_bool_dtype(series): return "boolean"
    if pd.api.types.is_datetime64_any_dtype(series): return "datetime"
    if pd.api.types.is_numeric_dtype(series):
        unique = int(series.nunique(dropna=True))
        if unique <= 2: return "binary_numeric"
        if unique <= 12 and pd.api.types.is_integer_dtype(series): return "categorical_numeric"
        return "numeric"
    unique = int(series.nunique(dropna=True))
    if unique <= 20: return "categorical"
    return "text"


def dataset_schema(df) -> dict[str, Any]:
    rows = int(len(df))
    columns = []
    for name in df.columns:
        s = df[name]
        nonnull = int(s.notna().sum())
        unique = int(s.nunique(dropna=True))
        columns.append({
            "name": str(name),
            "type": _dtype_label(s),
            "non_missing": nonnull,
            "missing": rows - nonnull,
            "missing_percent": round((rows - nonnull) * 100.0 / max(1, rows), 2),
            "unique": unique,
        })
    return {"rows": rows, "columns": columns, "column_count": len(columns), "duplicate_rows": int(df.duplicated().sum())}


def save_dataset(project_id: str, filename: str, content: bytes) -> dict[str, Any]:
    if not content:
        raise ValueError("The uploaded dataset is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Dataset is larger than the {MAX_UPLOAD_BYTES // (1024*1024)} MB upload limit.")
    df = _load_dataframe(filename, content)
    schema = dataset_schema(df)
    dataset_id = str(uuid.uuid4())
    suffix = str(filename).rsplit(".", 1)[-1].lower() if "." in str(filename) else "unknown"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO analysis_datasets (id, project_id, filename, file_type, content_b64, schema_json) VALUES (?, ?, ?, ?, ?, ?)",
            (dataset_id, project_id, str(filename)[:255], suffix, _compress(content), json.dumps(schema)),
        )
        conn.commit()
    return {"id": dataset_id, "project_id": project_id, "filename": filename, "file_type": suffix, "schema": schema}


def list_datasets(project_id: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, project_id, filename, file_type, schema_json, created_at, updated_at FROM analysis_datasets WHERE project_id = ? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try: item["schema"] = json.loads(item.pop("schema_json") or "{}")
        except Exception: item["schema"] = {}
        out.append(item)
    return out


def load_dataset(project_id: str, dataset_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM analysis_datasets WHERE id = ? AND project_id = ?", (dataset_id, project_id)).fetchone()
    if not row:
        raise ValueError("Analysis dataset not found for this project.")
    item = dict(row)
    return _load_dataframe(item["filename"], _decompress(item["content_b64"])), item


def _safe_float(value: Any) -> float | None:
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def _records(frame, limit: int = 250) -> list[dict[str, Any]]:
    out = []
    for row in frame.head(limit).to_dict(orient="records"):
        out.append({str(k): (_safe_float(v) if isinstance(v, (int, float)) else (None if v is None else str(v))) for k, v in row.items()})
    return out


def data_quality(df) -> dict[str, Any]:
    import pandas as pd
    schema = dataset_schema(df)
    numeric = df.select_dtypes(include="number")
    constant = [str(c) for c in df.columns if df[c].nunique(dropna=True) <= 1]
    high_missing = [item["name"] for item in schema["columns"] if item["missing_percent"] >= 20]
    numeric_outliers = []
    for col in numeric.columns:
        s = pd.to_numeric(numeric[col], errors="coerce").dropna()
        if len(s) < 8: continue
        q1, q3 = s.quantile([0.25, 0.75])
        iqr = q3 - q1
        if not math.isfinite(float(iqr)) or float(iqr) == 0: continue
        count = int(((s < q1 - 1.5*iqr) | (s > q3 + 1.5*iqr)).sum())
        numeric_outliers.append({"variable": str(col), "iqr_outliers": count, "percent": round(count*100/max(1,len(s)),2)})
    return {**schema, "constant_columns": constant, "high_missing_columns": high_missing, "numeric_outliers": numeric_outliers}


def descriptive_statistics(df) -> dict[str, Any]:
    import pandas as pd
    numeric = df.select_dtypes(include="number")
    rows = []
    for col in numeric.columns:
        s = pd.to_numeric(numeric[col], errors="coerce").dropna()
        if s.empty: continue
        rows.append({
            "variable": str(col), "n": int(s.size), "mean": _safe_float(s.mean()), "sd": _safe_float(s.std(ddof=1)),
            "median": _safe_float(s.median()), "minimum": _safe_float(s.min()), "maximum": _safe_float(s.max()),
            "skewness": _safe_float(s.skew()), "kurtosis": _safe_float(s.kurt()),
        })
    categorical = []
    for col in df.columns:
        if col in numeric.columns: continue
        vc = df[col].astype("string").fillna("<missing>").value_counts(dropna=False).head(20)
        categorical.append({"variable": str(col), "levels": [{"value": str(k), "count": int(v), "percent": round(int(v)*100/max(1,len(df)),2)} for k,v in vc.items()]})
    return {"numeric": rows, "categorical": categorical}


def cronbach_alpha(df, items: list[str]) -> dict[str, Any]:
    import numpy as np
    data = df[items].apply(lambda s: __import__("pandas").to_numeric(s, errors="coerce")).dropna()
    k = len(items)
    if k < 2 or len(data) < 5:
        raise ValueError("Cronbach alpha requires at least two items and five complete cases.")
    item_var = data.var(axis=0, ddof=1).sum()
    total_var = data.sum(axis=1).var(ddof=1)
    alpha = (k/(k-1)) * (1 - item_var/total_var) if total_var else float("nan")
    return {"items": items, "n_complete": int(len(data)), "alpha": _safe_float(alpha)}


def _coerce_numeric(df, columns: list[str]):
    import pandas as pd
    data = df[columns].copy()
    for c in columns: data[c] = pd.to_numeric(data[c], errors="coerce")
    return data.dropna()


def _regression_diagnostics(model, X, residuals) -> dict[str, Any]:
    import numpy as np
    from statsmodels.stats.diagnostic import acorr_breusch_godfrey, het_breuschpagan, het_white, linear_reset
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    out: dict[str, Any] = {}
    try:
        bp = het_breuschpagan(residuals, model.model.exog)
        out["breusch_pagan"] = {"lm_stat": _safe_float(bp[0]), "lm_pvalue": _safe_float(bp[1]), "f_stat": _safe_float(bp[2]), "f_pvalue": _safe_float(bp[3])}
    except Exception: pass
    try:
        wh = het_white(residuals, model.model.exog)
        out["white"] = {"lm_stat": _safe_float(wh[0]), "lm_pvalue": _safe_float(wh[1]), "f_stat": _safe_float(wh[2]), "f_pvalue": _safe_float(wh[3])}
    except Exception: pass
    try:
        bg = acorr_breusch_godfrey(model, nlags=min(4, max(1, int(math.sqrt(max(1, model.nobs)))//2)))
        out["breusch_godfrey"] = {"lm_stat": _safe_float(bg[0]), "lm_pvalue": _safe_float(bg[1]), "f_stat": _safe_float(bg[2]), "f_pvalue": _safe_float(bg[3])}
    except Exception: pass
    try:
        jb = jarque_bera(residuals)
        out["jarque_bera"] = {"statistic": _safe_float(jb[0]), "pvalue": _safe_float(jb[1]), "skewness": _safe_float(jb[2]), "kurtosis": _safe_float(jb[3])}
    except Exception: pass
    try: out["durbin_watson"] = _safe_float(durbin_watson(residuals))
    except Exception: pass
    try:
        reset = linear_reset(model, power=2, use_f=True)
        out["ramsey_reset"] = {"statistic": _safe_float(reset.fvalue), "pvalue": _safe_float(reset.pvalue)}
    except Exception: pass
    try:
        vals=[]
        arr = np.asarray(X, dtype=float)
        for idx,name in enumerate(list(X.columns)):
            if str(name).lower() in {"const","intercept"}: continue
            vals.append({"variable":str(name),"vif":_safe_float(variance_inflation_factor(arr, idx))})
        out["vif"] = vals
    except Exception: pass
    try:
        from statsmodels.stats.outliers_influence import OLSInfluence
        infl=OLSInfluence(model); cooks=infl.cooks_distance[0]; lev=infl.hat_matrix_diag
        out["influence"]={"max_cooks_distance":_safe_float(max(cooks)),"max_leverage":_safe_float(max(lev)),"cooks_over_4n":int((cooks>4/max(1,len(cooks))).sum())}
    except Exception: pass
    return out


def _parameter_table(model) -> list[dict[str, Any]]:
    names = list(getattr(model.params, "index", range(len(model.params))))
    conf = model.conf_int()
    out=[]
    for i,name in enumerate(names):
        ci = conf.iloc[i] if hasattr(conf,"iloc") else conf[i]
        out.append({"term":str(name),"coefficient":_safe_float(model.params.iloc[i] if hasattr(model.params,"iloc") else model.params[i]),"std_error":_safe_float(model.bse.iloc[i] if hasattr(model.bse,"iloc") else model.bse[i]),"statistic":_safe_float(model.tvalues.iloc[i] if hasattr(model.tvalues,"iloc") else model.tvalues[i]),"pvalue":_safe_float(model.pvalues.iloc[i] if hasattr(model.pvalues,"iloc") else model.pvalues[i]),"ci_low":_safe_float(ci[0]),"ci_high":_safe_float(ci[1])})
    return out


def run_ols(df, dependent: str, predictors: list[str], robust: bool = False) -> dict[str, Any]:
    import statsmodels.api as sm
    data = _coerce_numeric(df, [dependent] + predictors)
    if len(data) < max(10, len(predictors)+5): raise ValueError("Not enough complete cases for the requested OLS model.")
    X = sm.add_constant(data[predictors], has_constant="add")
    fit = sm.OLS(data[dependent], X).fit(cov_type="HC3" if robust else "nonrobust")
    return {"analysis":"ols","n":int(fit.nobs),"dependent":dependent,"predictors":predictors,"robust_hc3":bool(robust),"model":{"r_squared":_safe_float(fit.rsquared),"adjusted_r_squared":_safe_float(fit.rsquared_adj),"f_statistic":_safe_float(fit.fvalue),"f_pvalue":_safe_float(fit.f_pvalue),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic)},"parameters":_parameter_table(fit),"diagnostics":_regression_diagnostics(fit,X,fit.resid)}


def run_glm(df, dependent: str, predictors: list[str], family: str) -> dict[str, Any]:
    import statsmodels.api as sm
    data = _coerce_numeric(df, [dependent] + predictors)
    X = sm.add_constant(data[predictors], has_constant="add")
    fam = family.lower()
    if fam == "logistic": family_obj = sm.families.Binomial()
    elif fam == "poisson": family_obj = sm.families.Poisson()
    elif fam in {"negative_binomial","negbin"}: family_obj = sm.families.NegativeBinomial()
    else: raise ValueError("Unsupported GLM family.")
    fit = sm.GLM(data[dependent], X, family=family_obj).fit()
    params=[]
    conf=fit.conf_int()
    for i,name in enumerate(fit.params.index):
        b=float(fit.params.iloc[i]); ci=conf.iloc[i]
        params.append({"term":str(name),"coefficient":_safe_float(b),"std_error":_safe_float(fit.bse.iloc[i]),"statistic":_safe_float(fit.tvalues.iloc[i]),"pvalue":_safe_float(fit.pvalues.iloc[i]),"ci_low":_safe_float(ci.iloc[0]),"ci_high":_safe_float(ci.iloc[1]),"exp_coefficient":_safe_float(math.exp(b)) if abs(b)<700 else None})
    dispersion=float(fit.pearson_chi2/max(1,fit.df_resid)) if getattr(fit,"df_resid",0) else None
    diagnostics={"converged":bool(getattr(fit,"converged",True)),"pearson_dispersion":_safe_float(dispersion)}
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        import numpy as np
        arr=np.asarray(X,float); diagnostics["vif"]=[{"variable":str(name),"vif":_safe_float(variance_inflation_factor(arr,i))} for i,name in enumerate(X.columns) if str(name).lower() not in {"const","intercept"}]
    except Exception: pass
    if fam=="logistic":
        try:
            pred=fit.predict(X); diagnostics["predicted_probability_range"]={"min":_safe_float(pred.min()),"max":_safe_float(pred.max())}
            diagnostics["outcome_levels"]=[str(x) for x in sorted(data[dependent].dropna().unique())]
        except Exception: pass
    if fam in {"poisson","negative_binomial","negbin"}:
        diagnostics["count_outcome_check"]={"minimum":_safe_float(data[dependent].min()),"non_integer_count":int(((data[dependent]-data[dependent].round()).abs()>1e-9).sum()),"zero_count":int((data[dependent]==0).sum())}
    return {"analysis":fam,"n":int(fit.nobs),"dependent":dependent,"predictors":predictors,"model":{"deviance":_safe_float(fit.deviance),"pearson_chi2":_safe_float(fit.pearson_chi2),"aic":_safe_float(fit.aic),"bic":_safe_float(getattr(fit,"bic_llf",None))},"parameters":params,"diagnostics":diagnostics}


def run_mediation(df, x: str, mediator: str, y: str, covariates: list[str] | None = None, bootstrap: int = 1000, seed: int = 20260816) -> dict[str, Any]:
    import numpy as np
    import statsmodels.api as sm
    covariates = covariates or []
    cols=[x,mediator,y]+covariates
    data=_coerce_numeric(df, cols)
    Xm=sm.add_constant(data[[x]+covariates],has_constant="add"); mfit=sm.OLS(data[mediator],Xm).fit()
    Xy=sm.add_constant(data[[x,mediator]+covariates],has_constant="add"); yfit=sm.OLS(data[y],Xy).fit()
    Xt=sm.add_constant(data[[x]+covariates],has_constant="add"); tfit=sm.OLS(data[y],Xt).fit()
    a=float(mfit.params[x]); b=float(yfit.params[mediator]); direct=float(yfit.params[x]); total=float(tfit.params[x]); indirect=a*b
    rng=np.random.default_rng(seed); boot=[]; n=len(data)
    for _ in range(max(200,min(int(bootstrap),5000))):
        sample=data.iloc[rng.integers(0,n,n)]
        try:
            af=sm.OLS(sample[mediator],sm.add_constant(sample[[x]+covariates],has_constant="add")).fit().params[x]
            bf=sm.OLS(sample[y],sm.add_constant(sample[[x,mediator]+covariates],has_constant="add")).fit().params[mediator]
            boot.append(float(af*bf))
        except Exception: continue
    low,high=(np.percentile(boot,[2.5,97.5]) if boot else [float("nan"),float("nan")])
    return {"analysis":"mediation","n":int(n),"x":x,"mediator":mediator,"y":y,"covariates":covariates,"effects":{"a":_safe_float(a),"b":_safe_float(b),"direct":_safe_float(direct),"indirect":_safe_float(indirect),"total":_safe_float(total),"bootstrap_ci_low":_safe_float(low),"bootstrap_ci_high":_safe_float(high),"bootstrap_draws":len(boot)},"models":{"mediator_parameters":_parameter_table(mfit),"outcome_parameters":_parameter_table(yfit)}}


def run_moderation(df, x: str, moderator: str, y: str, covariates: list[str] | None = None, center: bool = True) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    covariates=covariates or []
    data=_coerce_numeric(df,[x,moderator,y]+covariates)
    xv=data[x].copy(); mv=data[moderator].copy()
    if center:
        xv=xv-xv.mean(); mv=mv-mv.mean()
    work=pd.DataFrame({x:xv,moderator:mv,"interaction":xv*mv})
    for c in covariates: work[c]=data[c]
    X=sm.add_constant(work,has_constant="add"); fit=sm.OLS(data[y],X).fit()
    mmean=float(data[moderator].mean()); msd=float(data[moderator].std(ddof=1)); b0=float(fit.params[x]); bi=float(fit.params["interaction"])
    slopes=[]
    for label,mv0 in [("low_-1sd",mmean-msd),("mean",mmean),("high_+1sd",mmean+msd)]:
        mcent=mv0-mmean if center else mv0; slopes.append({"level":label,"moderator_value":_safe_float(mv0),"simple_slope":_safe_float(b0+bi*mcent)})
    return {"analysis":"moderation","n":int(fit.nobs),"x":x,"moderator":moderator,"y":y,"centered":center,"parameters":_parameter_table(fit),"simple_slopes":slopes,"model":{"r_squared":_safe_float(fit.rsquared),"adjusted_r_squared":_safe_float(fit.rsquared_adj)}}


def run_time_series(df, dependent: str, time_variable: str, model_type: str = "arima", order: list[int] | None = None, seasonal_order: list[int] | None = None, exogenous: list[str] | None = None, lags: int = 1) -> dict[str, Any]:
    import pandas as pd
    from statsmodels.tsa.stattools import adfuller, kpss
    model_type=model_type.lower(); exogenous=exogenous or []
    data=df[[time_variable,dependent]+exogenous].copy()
    data[time_variable]=pd.to_datetime(data[time_variable],errors="coerce")
    for c in [dependent]+exogenous: data[c]=pd.to_numeric(data[c],errors="coerce")
    data=data.dropna().sort_values(time_variable).set_index(time_variable)
    y=data[dependent]
    if len(y)<20: raise ValueError("Time-series analysis requires at least 20 usable observations.")
    tests={}
    try:
        adf=adfuller(y,autolag="AIC"); tests["adf"]={"statistic":_safe_float(adf[0]),"pvalue":_safe_float(adf[1]),"lags":int(adf[2]),"nobs":int(adf[3])}
    except Exception: pass
    try:
        kt=kpss(y,regression="c",nlags="auto"); tests["kpss"]={"statistic":_safe_float(kt[0]),"pvalue":_safe_float(kt[1]),"lags":int(kt[2])}
    except Exception: pass
    if model_type in {"arima","sarimax"}:
        from statsmodels.tsa.statespace.sarimax import SARIMAX
        p,d,q=(order or [1,0,0])[:3]; sorder=(seasonal_order or [0,0,0,0])[:4]
        exog=data[exogenous] if exogenous else None
        fit=SARIMAX(y,exog=exog,order=(int(p),int(d),int(q)),seasonal_order=tuple(map(int,sorder)),enforce_stationarity=False,enforce_invertibility=False).fit(disp=False)
        params=[{"term":str(k),"coefficient":_safe_float(v),"pvalue":_safe_float(fit.pvalues.get(k))} for k,v in fit.params.items()]
        diag={}
        try:
            from statsmodels.stats.diagnostic import acorr_ljungbox
            lb=acorr_ljungbox(fit.resid.dropna(),lags=[min(10,max(2,len(fit.resid.dropna())//10))],return_df=True).iloc[-1]
            diag["ljung_box"]={"statistic":_safe_float(lb["lb_stat"]),"pvalue":_safe_float(lb["lb_pvalue"])}
        except Exception: pass
        try:
            from statsmodels.stats.stattools import jarque_bera
            jb=jarque_bera(fit.resid.dropna()); diag["jarque_bera"]={"statistic":_safe_float(jb[0]),"pvalue":_safe_float(jb[1]),"skewness":_safe_float(jb[2]),"kurtosis":_safe_float(jb[3])}
        except Exception: pass
        try:
            diag["ar_roots_modulus"]=[_safe_float(abs(x)) for x in fit.arroots]
            diag["ma_roots_modulus"]=[_safe_float(abs(x)) for x in fit.maroots]
        except Exception: pass
        return {"analysis":"time_series","model_type":model_type,"n":int(len(y)),"time_variable":time_variable,"dependent":dependent,"exogenous":exogenous,"stationarity":tests,"model":{"order":[int(p),int(d),int(q)],"seasonal_order":list(map(int,sorder)),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic),"hqic":_safe_float(fit.hqic)},"parameters":params,"diagnostics":diag,"fitted_preview":[{"time":str(idx),"actual":_safe_float(y.loc[idx]),"fitted":_safe_float(fit.fittedvalues.loc[idx])} for idx in y.index[-30:]]}
    if model_type == "var":
        from statsmodels.tsa.api import VAR
        vars_=[dependent]+exogenous
        if len(vars_)<2: raise ValueError("VAR requires at least two endogenous series. Add another series under predictors/exogenous variables.")
        work=data[vars_].dropna(); fit=VAR(work).fit(maxlags=max(1,int(lags)),ic=None)
        equations=[]
        for eq in vars_:
            eqrows=[]
            for term in fit.params.index:
                eqrows.append({"term":str(term),"coefficient":_safe_float(fit.params.loc[term,eq]),"pvalue":_safe_float(fit.pvalues.loc[term,eq])})
            equations.append({"equation":eq,"parameters":eqrows,"r_squared":None})
        diag={"stable":bool(fit.is_stable()),"roots_modulus":[_safe_float(abs(x)) for x in fit.roots]}
        try:
            wt=fit.test_whiteness(nlags=max(5,int(fit.k_ar)+2)); diag["whiteness"]={"statistic":_safe_float(wt.test_statistic),"pvalue":_safe_float(wt.pvalue)}
        except Exception: pass
        try:
            nt=fit.test_normality(); diag["normality"]={"statistic":_safe_float(nt.test_statistic),"pvalue":_safe_float(nt.pvalue)}
        except Exception: pass
        return {"analysis":"time_series","model_type":"var","n":int(fit.nobs),"time_variable":time_variable,"variables":vars_,"stationarity":tests,"model":{"lags":int(fit.k_ar),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic),"hqic":_safe_float(fit.hqic)},"equations":equations,"diagnostics":diag}
    raise ValueError("Unsupported time-series model. Use ARIMA, SARIMAX or VAR.")


def run_panel(df, dependent: str, predictors: list[str], entity: str, time_variable: str, model_type: str = "fixed_effects") -> dict[str, Any]:
    """Panel estimators with explicit entity/time structure and diagnostics.

    Uses statsmodels-only estimators so the core Render build is deterministic.
    Entity/time/two-way fixed effects use LSDV with entity-clustered SEs. Random
    effects uses a random-intercept mixed model. The function reports panel
    balance, duplicate entity-time rows, within/between variation, a descriptive
    residual serial-correlation screen and a Hausman-style FE/RE comparison when
    the covariance difference is invertible.
    """
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    from scipy import stats
    cols=[entity,time_variable,dependent]+predictors
    data=df[cols].copy()
    for c in [dependent]+predictors: data[c]=pd.to_numeric(data[c],errors="coerce")
    data=data.dropna().copy()
    if data.empty: raise ValueError("No complete panel observations remain after removing missing values.")
    duplicate_entity_time=int(data.duplicated([entity,time_variable]).sum())
    if duplicate_entity_time:
        raise ValueError(f"Panel identifiers are not unique: {duplicate_entity_time} duplicate entity-time rows were found. Resolve them before estimation.")
    if data[entity].nunique() < 2 or data[time_variable].nunique() < 2:
        raise ValueError("Panel regression requires at least two entities and two time periods.")
    mt=model_type.lower(); params=[]; model_summary={}; diagnostics={}; fit=None
    baseX=data[predictors].astype(float).reset_index(drop=True)
    groups=data[entity].reset_index(drop=True)
    y=data[dependent].astype(float).reset_index(drop=True)
    if mt in {"fixed","fixed_effects","fe","time_fixed_effects","two_way_fixed_effects","twfe"}:
        parts=[baseX]
        if mt in {"fixed","fixed_effects","fe","two_way_fixed_effects","twfe"}:
            parts.append(pd.get_dummies(data[entity].astype("string"),prefix="entity",drop_first=True,dtype=float).reset_index(drop=True))
        if mt in {"time_fixed_effects","two_way_fixed_effects","twfe"}:
            parts.append(pd.get_dummies(data[time_variable].astype("string"),prefix="time",drop_first=True,dtype=float).reset_index(drop=True))
        X=pd.concat(parts,axis=1); X=sm.add_constant(X,has_constant="add")
        fit=sm.OLS(y,X).fit(cov_type="cluster",cov_kwds={"groups":groups})
        names=[n for n in fit.params.index if not str(n).startswith("entity_") and not str(n).startswith("time_")]
        ci=fit.conf_int()
        for name in names:
            params.append({"term":str(name),"coefficient":_safe_float(fit.params[name]),"std_error":_safe_float(fit.bse[name]),"statistic":_safe_float(fit.tvalues[name]),"pvalue":_safe_float(fit.pvalues[name]),"ci_low":_safe_float(ci.loc[name].iloc[0]),"ci_high":_safe_float(ci.loc[name].iloc[1])})
        model_summary={"r_squared":_safe_float(fit.rsquared),"adjusted_r_squared":_safe_float(fit.rsquared_adj),"f_statistic":_safe_float(fit.fvalue),"f_pvalue":_safe_float(fit.f_pvalue)}
        label="two_way_fixed_effects" if mt in {"two_way_fixed_effects","twfe"} else "time_fixed_effects" if mt=="time_fixed_effects" else "fixed_effects"
    elif mt in {"random","random_effects","re"}:
        X=sm.add_constant(baseX,has_constant="add")
        fit=sm.MixedLM(y,X,groups=groups).fit(reml=False,method="lbfgs",disp=False)
        ci=fit.conf_int()
        for name in list(fit.fe_params.index):
            params.append({"term":str(name),"coefficient":_safe_float(fit.fe_params[name]),"std_error":_safe_float(fit.bse_fe[name]),"statistic":_safe_float(fit.tvalues[name]),"pvalue":_safe_float(fit.pvalues[name]),"ci_low":_safe_float(ci.loc[name].iloc[0]),"ci_high":_safe_float(ci.loc[name].iloc[1])})
        model_summary={"log_likelihood":_safe_float(fit.llf),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic),"group_variance":_safe_float(float(fit.cov_re.iloc[0,0])) if getattr(fit,"cov_re",None) is not None else None}
        label="random_effects"
    elif mt in {"pooled","pooled_ols"}:
        X=sm.add_constant(baseX,has_constant="add")
        fit=sm.OLS(y,X).fit(cov_type="cluster",cov_kwds={"groups":groups})
        params=_parameter_table(fit)
        model_summary={"r_squared":_safe_float(fit.rsquared),"adjusted_r_squared":_safe_float(fit.rsquared_adj),"f_statistic":_safe_float(fit.fvalue),"f_pvalue":_safe_float(fit.f_pvalue)}
        label="pooled_ols"
    else: raise ValueError("Panel model must be pooled OLS, entity fixed effects, time fixed effects, two-way fixed effects or random effects.")
    counts=data.groupby(entity)[time_variable].nunique(); diagnostics["balanced_panel"]=bool(counts.nunique()==1); diagnostics["observations_per_entity_min"]=int(counts.min()); diagnostics["observations_per_entity_max"]=int(counts.max()); diagnostics["duplicate_entity_time_rows"]=duplicate_entity_time
    variation=[]
    for c in [dependent]+predictors:
        overall=float(data[c].var(ddof=1)) if len(data)>1 else float("nan")
        within=float((data[c]-data.groupby(entity)[c].transform("mean")).var(ddof=1)) if len(data)>1 else float("nan")
        means=data.groupby(entity)[c].mean(); between=float(means.var(ddof=1)) if len(means)>1 else float("nan")
        variation.append({"variable":c,"overall_variance":_safe_float(overall),"within_variance":_safe_float(within),"between_variance":_safe_float(between)})
    diagnostics["within_between_variation"]=variation
    # Descriptive AR(1) screen within entity using model residuals when residuals align to rows.
    try:
        resid=np.asarray(fit.resid,float); temp=data[[entity,time_variable]].reset_index(drop=True).copy(); temp["resid"]=resid[:len(temp)]; pairs=[]
        for _,g in temp.sort_values([entity,time_variable]).groupby(entity):
            if len(g)>=3: pairs.extend(zip(g["resid"].iloc[:-1],g["resid"].iloc[1:]))
        if len(pairs)>=5:
            a=np.asarray([x for x,_ in pairs]); b=np.asarray([x for _,x in pairs]); diagnostics["within_entity_residual_ar1"]=_safe_float(np.corrcoef(a,b)[0,1])
    except Exception: pass
    # Hausman-style slope comparison between entity FE and random intercept.
    try:
        dummies=pd.get_dummies(data[entity].astype("string"),prefix="entity",drop_first=True,dtype=float).reset_index(drop=True)
        Xfe=sm.add_constant(pd.concat([baseX,dummies],axis=1),has_constant="add"); fe=sm.OLS(y,Xfe).fit()
        Xre=sm.add_constant(baseX,has_constant="add"); re=sm.MixedLM(y,Xre,groups=groups).fit(reml=False,method="lbfgs",disp=False)
        common=[c for c in predictors if c in fe.params.index and c in re.fe_params.index]
        if common:
            bdiff=np.asarray([fe.params[c]-re.fe_params[c] for c in common],float)
            vfe=fe.cov_params().loc[common,common].values; vre=re.cov_params().loc[common,common].values
            vdiff=vfe-vre; statv=float(bdiff.T@np.linalg.pinv(vdiff)@bdiff); pval=float(stats.chi2.sf(statv,len(common)))
            diagnostics["hausman_style_fe_re"]={"statistic":_safe_float(statv),"df":len(common),"pvalue":_safe_float(pval),"note":"A diagnostic FE/RE coefficient comparison. Treat cautiously if covariance-difference conditions are poor; substantive exogeneity assumptions still govern estimator choice."}
    except Exception as exc: diagnostics["hausman_style_fe_re"]={"available":False,"note":str(exc)}
    return {"analysis":"panel_regression","model_type":label,"n":int(len(data)),"entities":int(data[entity].nunique()),"periods":int(data[time_variable].nunique()),"dependent":dependent,"predictors":predictors,"entity":entity,"time_variable":time_variable,"parameters":params,"model":model_summary,"diagnostics":diagnostics}

def run_hierarchical_ols(df, dependent: str, blocks: list[list[str]]) -> dict[str, Any]:
    import statsmodels.api as sm
    from scipy import stats
    if not blocks or not any(blocks): raise ValueError("Hierarchical regression requires at least one predictor block.")
    seen=[]; models=[]; previous_fit=None
    final_diag={}
    for idx,block in enumerate(blocks,1):
        for v in block:
            if v and v not in seen: seen.append(v)
        data=_coerce_numeric(df,[dependent]+seen); X=sm.add_constant(data[seen],has_constant="add"); fit=sm.OLS(data[dependent],X).fit()
        delta_r2=float(fit.rsquared-(previous_fit.rsquared if previous_fit is not None else 0.0))
        change={}
        if previous_fit is not None and int(previous_fit.nobs)==int(fit.nobs):
            try:
                fstat,pval,dfdiff=fit.compare_f_test(previous_fit); change={"f_change":_safe_float(fstat),"pvalue":_safe_float(pval),"df_difference":_safe_float(dfdiff)}
            except Exception: pass
        models.append({"block":idx,"added_predictors":list(block),"all_predictors":list(seen),"r_squared":_safe_float(fit.rsquared),"r_squared_change":_safe_float(delta_r2),"adjusted_r_squared":_safe_float(fit.rsquared_adj),"change_test":change,"parameters":_parameter_table(fit)})
        previous_fit=fit; final_diag=_regression_diagnostics(fit,X,fit.resid)
    return {"analysis":"hierarchical_regression","dependent":dependent,"blocks":models,"n":int(previous_fit.nobs),"diagnostics":final_diag}

def run_multinomial(df, dependent: str, predictors: list[str]) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    work=df[[dependent]+predictors].copy().dropna()
    ycat=pd.Categorical(work[dependent]); y=pd.Series(ycat.codes,index=work.index)
    if len(ycat.categories)<3: raise ValueError("Multinomial regression requires an outcome with at least three categories.")
    X=sm.add_constant(work[predictors].apply(pd.to_numeric,errors="coerce"),has_constant="add"); valid=X.notna().all(axis=1); X=X.loc[valid]; y=y.loc[valid]
    fit=sm.MNLogit(y,X).fit(disp=False,maxiter=200)
    rows=[]
    for outcome_idx in fit.params.columns:
        label=str(ycat.categories[int(outcome_idx)+1]) if int(outcome_idx)+1<len(ycat.categories) else str(outcome_idx)
        for term in fit.params.index:
            b=float(fit.params.loc[term,outcome_idx]); se=float(fit.bse.loc[term,outcome_idx]); p=float(fit.pvalues.loc[term,outcome_idx])
            rows.append({"outcome_category":label,"term":str(term),"coefficient":_safe_float(b),"std_error":_safe_float(se),"pvalue":_safe_float(p),"relative_risk_ratio":_safe_float(math.exp(b)) if abs(b)<700 else None})
    diagnostics={"converged":bool((getattr(fit,"mle_retvals",{}) or {}).get("converged",True)),"category_counts":{str(k):int(v) for k,v in work[dependent].value_counts().items()},"iia_note":"Independence of irrelevant alternatives is a substantive/model assumption; compare alternative specifications when close-substitute outcome categories are plausible."}
    return {"analysis":"multinomial_logistic","n":int(len(y)),"dependent":dependent,"categories":[str(x) for x in ycat.categories],"predictors":predictors,"model":{"log_likelihood":_safe_float(fit.llf),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic)},"parameters":rows,"diagnostics":diagnostics}


def run_ordinal(df, dependent: str, predictors: list[str]) -> dict[str, Any]:
    import pandas as pd
    from statsmodels.miscmodels.ordinal_model import OrderedModel
    work=df[[dependent]+predictors].copy().dropna()
    y=pd.Categorical(work[dependent],ordered=True).codes
    X=work[predictors].apply(pd.to_numeric,errors="coerce"); valid=X.notna().all(axis=1); X=X.loc[valid]; y=y[valid.to_numpy()]
    fit=OrderedModel(y,X,distr="logit").fit(method="bfgs",disp=False)
    rows=[]
    for term in fit.params.index:
        rows.append({"term":str(term),"coefficient":_safe_float(fit.params[term]),"std_error":_safe_float(fit.bse[term]),"statistic":_safe_float(fit.tvalues[term]),"pvalue":_safe_float(fit.pvalues[term]),"odds_ratio":_safe_float(math.exp(float(fit.params[term]))) if term in predictors else None})
    diagnostics={"converged":bool((getattr(fit,"mle_retvals",{}) or {}).get("converged",True)),"proportional_odds_note":"Ordered logit assumes common slopes across thresholds. Review a parallel-lines/alternative specification sensitivity before strong substantive conclusions."}
    return {"analysis":"ordinal_logistic","n":int(len(y)),"dependent":dependent,"predictors":predictors,"model":{"log_likelihood":_safe_float(fit.llf),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic)},"parameters":rows,"diagnostics":diagnostics}


def run_multilevel(df, dependent: str, predictors: list[str], group: str) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    work=df[[dependent,group]+predictors].copy().dropna()
    for c in [dependent]+predictors: work[c]=pd.to_numeric(work[c],errors="coerce")
    work=work.dropna(); X=sm.add_constant(work[predictors],has_constant="add")
    if work[group].nunique()<3: raise ValueError("Multilevel modelling requires at least three groups/clusters.")
    fit=sm.MixedLM(work[dependent],X,groups=work[group]).fit(reml=False,method="lbfgs",disp=False)
    ci=fit.conf_int(); rows=[]
    for name in fit.fe_params.index:
        rows.append({"term":str(name),"coefficient":_safe_float(fit.fe_params[name]),"std_error":_safe_float(fit.bse_fe[name]),"statistic":_safe_float(fit.tvalues[name]),"pvalue":_safe_float(fit.pvalues[name]),"ci_low":_safe_float(ci.loc[name].iloc[0]),"ci_high":_safe_float(ci.loc[name].iloc[1])})
    return {"analysis":"multilevel_random_intercept","n":int(len(work)),"groups":int(work[group].nunique()),"group_variable":group,"dependent":dependent,"predictors":predictors,"parameters":rows,"model":{"log_likelihood":_safe_float(fit.llf),"aic":_safe_float(fit.aic),"bic":_safe_float(fit.bic),"group_variance":_safe_float(float(fit.cov_re.iloc[0,0]))}}


def run_moderated_mediation(df, x: str, mediator: str, moderator: str, y: str, covariates: list[str] | None = None, bootstrap: int = 1000, seed: int = 20260816) -> dict[str, Any]:
    """Conditional indirect effect where moderator changes the X→M path (PROCESS-style model 7 analogue)."""
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    covariates=covariates or []
    data=_coerce_numeric(df,[x,mediator,moderator,y]+covariates)
    xc=data[x]-data[x].mean(); wc=data[moderator]-data[moderator].mean(); interaction=xc*wc
    Xm=pd.DataFrame({x:xc,moderator:wc,"x_by_w":interaction},index=data.index)
    for c in covariates: Xm[c]=data[c]
    mfit=sm.OLS(data[mediator],sm.add_constant(Xm,has_constant="add")).fit()
    Xy=sm.add_constant(data[[x,mediator]+covariates],has_constant="add"); yfit=sm.OLS(data[y],Xy).fit(); b=float(yfit.params[mediator])
    mmean=float(data[moderator].mean()); msd=float(data[moderator].std(ddof=1)); a1=float(mfit.params[x]); a3=float(mfit.params["x_by_w"])
    conditional=[]
    for label,w in [("low_-1sd",mmean-msd),("mean",mmean),("high_+1sd",mmean+msd)]:
        wcval=w-mmean; conditional.append({"level":label,"moderator_value":_safe_float(w),"conditional_indirect_effect":_safe_float((a1+a3*wcval)*b)})
    rng=np.random.default_rng(seed); n=len(data); boot={x["level"]:[] for x in conditional}
    draws=max(200,min(int(bootstrap),3000))
    for _ in range(draws):
        samp=data.iloc[rng.integers(0,n,n)].copy(); xcs=samp[x]-samp[x].mean(); wcs=samp[moderator]-samp[moderator].mean(); Xms=pd.DataFrame({x:xcs,moderator:wcs,"x_by_w":xcs*wcs},index=samp.index)
        for c in covariates: Xms[c]=samp[c]
        try:
            mf=sm.OLS(samp[mediator],sm.add_constant(Xms,has_constant="add")).fit(); yf=sm.OLS(samp[y],sm.add_constant(samp[[x,mediator]+covariates],has_constant="add")).fit(); bb=float(yf.params[mediator]); aa1=float(mf.params[x]); aa3=float(mf.params["x_by_w"]); mm=float(samp[moderator].mean()); ss=float(samp[moderator].std(ddof=1))
            for label,w in [("low_-1sd",mm-ss),("mean",mm),("high_+1sd",mm+ss)]: boot[label].append((aa1+aa3*(w-mm))*bb)
        except Exception: continue
    for item in conditional:
        arr=boot[item["level"]]
        if arr:
            lo,hi=np.percentile(arr,[2.5,97.5]); item["bootstrap_ci_low"]=_safe_float(lo); item["bootstrap_ci_high"]=_safe_float(hi)
    return {"analysis":"moderated_mediation","n":int(n),"x":x,"mediator":mediator,"moderator":moderator,"y":y,"covariates":covariates,"a_path_parameters":_parameter_table(mfit),"outcome_parameters":_parameter_table(yfit),"conditional_indirect_effects":conditional,"bootstrap_draws":draws}


def run_sem(df, model_spec: str) -> dict[str, Any]:
    try:
        from semopy import Model, calc_stats
    except Exception as exc:
        raise RuntimeError("Full latent-variable SEM requires semopy. The deployment must install the Data & Analysis dependencies before SEM can run; ProjectReady will not substitute ordinary regression and label it SEM.") from exc
    import pandas as pd
    spec=str(model_spec or "").strip()
    if not spec: raise ValueError("Provide SEM model syntax, for example: Leadership =~ L1 + L2 + L3; Performance ~ Leadership + Motivation")
    # Determine referenced variables conservatively from syntax.
    tokens=set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_.]*\b",spec)); operators={"DEFINE","START","BOUND","CONSTRAINT","ordinal"}
    cols=[c for c in df.columns if str(c) in tokens and str(c) not in operators]
    work=df[cols].copy() if cols else df.copy()
    for c in work.columns: work[c]=pd.to_numeric(work[c],errors="coerce")
    work=work.dropna()
    if len(work)<30: raise ValueError("SEM requires at least 30 complete observations for the variables in the model specification.")
    model=Model(spec); model.fit(work)
    est=model.inspect(std_est=True)
    stats=calc_stats(model)
    fit_stats={}
    for key in ["DoF","chi2","chi2 p-value","CFI","TLI","RMSEA","SRMR","AIC","BIC"]:
        try:
            val=stats.loc["Value",key] if "Value" in stats.index else stats[key].iloc[0]
            fit_stats[key]=_safe_float(val)
        except Exception: pass
    paths=[]
    for _,row in est.iterrows():
        op=str(row.get("op") or ""); left=str(row.get("lval") or ""); right=str(row.get("rval") or "")
        if op not in {"~","=~"}: continue
        paths.append({"from":right if op=="~" else left,"to":left if op=="~" else right,"operator":op,"estimate":_safe_float(row.get("Estimate")),"std_estimate":_safe_float(row.get("Est. Std")),"std_error":_safe_float(row.get("Std. Err")),"z_value":_safe_float(row.get("z-value")),"pvalue":_safe_float(row.get("p-value"))})
    diagram=sem_path_diagram_svg(paths)
    return {"analysis":"sem","n":int(len(work)),"model_spec":spec,"fit":fit_stats,"paths":paths,"diagram_svg":diagram}


def sem_path_diagram_svg(paths: list[dict[str, Any]]) -> str:
    """Create a publication-clean, self-contained SVG SEM/path diagram.

    Adjacent-level paths are straight. Paths that skip a layer are curved so
    they do not run through intervening constructs. Latent constructs are shown
    as ellipses when measurement paths (=~) are present; observed variables are
    rounded rectangles. Coefficients always come from the fitted result object.
    """
    nodes=[]
    latent=set()
    for p in paths:
        a,b=str(p.get("from") or ""),str(p.get("to") or "")
        if str(p.get("operator") or "") == "=~": latent.add(a)
        for name in (a,b):
            if name and name not in nodes: nodes.append(name)
    if not nodes:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='900' height='260'><rect width='100%' height='100%' fill='white'/><text x='40' y='80' font-family='Arial' font-size='22'>No estimable SEM paths to display.</text></svg>"
    indeg={n:0 for n in nodes}
    for p in paths:
        a,b=str(p.get("from") or ""),str(p.get("to") or "")
        if a!=b and b in indeg: indeg[b]+=1
    roots=[n for n in nodes if indeg[n]==0] or nodes[:1]
    level={n:0 for n in roots}
    for _ in range(len(nodes)+3):
        changed=False
        for p in paths:
            a,b=str(p.get("from") or ""),str(p.get("to") or "")
            if a==b: continue
            if a in level and (b not in level or level[b] < level[a]+1):
                level[b]=level[a]+1; changed=True
        if not changed: break
    for n in nodes: level.setdefault(n,0)
    maxlevel=max(level.values()) if level else 0
    grouped={l:[n for n in nodes if level[n]==l] for l in range(maxlevel+1)}
    width=max(1050,310*(maxlevel+1)); max_group=max(len(v) for v in grouped.values()); height=max(440,145*max_group+80)
    positions={}
    for l,grp in grouped.items():
        x=145+(width-290)*(l/max(1,maxlevel)) if maxlevel else width/2
        for i,n in enumerate(grp): positions[n]=(x,70+(i+1)*(height-140)/(len(grp)+1))
    parts=[f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>",
           "<defs><marker id='arrow' markerWidth='10' markerHeight='8' refX='9' refY='4' orient='auto'><polygon points='0 0, 10 4, 0 8' fill='#25324a'/></marker><filter id='softShadow' x='-20%' y='-20%' width='140%' height='140%'><feDropShadow dx='0' dy='2' stdDeviation='2' flood-color='#182235' flood-opacity='.10'/></filter></defs>",
           "<rect width='100%' height='100%' fill='white' rx='18'/>"]
    for p in paths:
        a,b=str(p.get("from") or ""),str(p.get("to") or "")
        if a not in positions or b not in positions or a==b: continue
        x1,y1=positions[a]; x2,y2=positions[b]
        dx=x2-x1; sign=1 if dx>=0 else -1; startx=x1+sign*106; endx=x2-sign*106
        skip=abs(level.get(b,0)-level.get(a,0))>1
        if skip:
            lift=max(70,min(130,abs(dx)*.18)); control_y=max(34,min(y1,y2)-lift)
            d=f"M {startx:.1f},{y1:.1f} C {(startx+endx)/2:.1f},{control_y:.1f} {(startx+endx)/2:.1f},{control_y:.1f} {endx:.1f},{y2:.1f}"
            parts.append(f"<path d='{d}' fill='none' stroke='#25324a' stroke-width='2.2' marker-end='url(#arrow)'/>")
            mx=(startx+endx)/2; my=control_y-7
        else:
            parts.append(f"<line x1='{startx:.1f}' y1='{y1:.1f}' x2='{endx:.1f}' y2='{y2:.1f}' stroke='#25324a' stroke-width='2.2' marker-end='url(#arrow)'/>")
            mx=(startx+endx)/2; my=(y1+y2)/2-15
        est=p.get("std_estimate") if p.get("std_estimate") is not None else p.get("estimate")
        label="" if est is None else f"β={float(est):.3f}"
        pv=p.get("pvalue")
        if pv is not None:
            pvf=float(pv); label += "  p<.001" if pvf<.001 else f"  p={pvf:.3f}"
        if label:
            label_width=max(112,min(190,7.2*len(label)+18))
            parts.append(f"<rect x='{mx-label_width/2:.1f}' y='{my-17:.1f}' width='{label_width:.1f}' height='28' rx='8' fill='white' stroke='#e1e6ee' stroke-width='1'/><text x='{mx:.1f}' y='{my+2:.1f}' text-anchor='middle' font-family='Arial, sans-serif' font-size='13' fill='#344054'>{_xml(label)}</text>")
    for n,(x,y) in positions.items():
        if n in latent:
            parts.append(f"<ellipse cx='{x:.1f}' cy='{y:.1f}' rx='108' ry='38' fill='#f7f9fc' stroke='#25324a' stroke-width='2'/>")
        else:
            parts.append(f"<rect x='{x-108:.1f}' y='{y-35:.1f}' width='216' height='70' rx='15' fill='#f7f9fc' stroke='#25324a' stroke-width='2'/>")
        # Wrap long labels into two lines at a word boundary.
        words=n.split(); lines=[n]
        if len(n)>22 and len(words)>1:
            pivot=max(1,len(words)//2); lines=[" ".join(words[:pivot])," ".join(words[pivot:])]
        if len(lines)==1:
            parts.append(f"<text x='{x:.1f}' y='{y+5:.1f}' text-anchor='middle' font-family='Arial, sans-serif' font-size='15' font-weight='600' fill='#182235'>{_xml(lines[0])}</text>")
        else:
            parts.append(f"<text x='{x:.1f}' y='{y-3:.1f}' text-anchor='middle' font-family='Arial, sans-serif' font-size='14' font-weight='600' fill='#182235'><tspan x='{x:.1f}' dy='0'>{_xml(lines[0])}</tspan><tspan x='{x:.1f}' dy='18'>{_xml(lines[1])}</tspan></text>")
    parts.append("<text x='24' y='28' font-family='Arial, sans-serif' font-size='12' fill='#667085'>ProjectReady verified SEM/path estimates</text></svg>")
    return "".join(parts)


def _xml(text: Any) -> str:
    return str(text or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("'","&apos;").replace('"',"&quot;")


def recommend_analysis(schema: dict[str, Any], objectives: list[str], framework_summary: str = "") -> list[dict[str, Any]]:
    text=" ".join(objectives+[framework_summary]).lower(); recommendations=[]
    def add(kind: str, reason: str):
        if not any(x.get("type")==kind for x in recommendations): recommendations.append({"type":kind,"reason":reason})
    if any(k in text for k in ["difference between two","compare two","t-test","t test"]): add("t_test","The objective explicitly compares two means or identifies a t-test.")
    if any(k in text for k in ["anova","compare three","compare groups"]): add("anova","The objective compares mean outcomes across multiple groups.")
    if any(k in text for k in ["ancova","adjusted mean","control for covariate"]): add("ancova","The objective compares groups while adjusting for covariates.")
    if any(k in text for k in ["manova","multiple dependent","multivariate analysis of variance"]): add("manova","The design indicates multiple outcomes tested jointly.")
    if any(k in text for k in ["network","centrality","community detection","nodes","edges"]): add("network","The objective concerns node/tie structure, centrality or communities.")
    if any(k in text for k in ["moderated mediation","conditional indirect"]): add("moderated_mediation","The research logic specifies a conditional indirect pathway.")
    if any(k in text for k in ["mediate","mediation","indirect"]): add("mediation","The research logic explicitly refers to mediation or an indirect pathway.")
    if any(k in text for k in ["moderate","moderation","interaction"]): add("moderation","The research logic explicitly refers to moderation or an interaction effect.")
    if any(k in text for k in ["structural equation","sem","latent","measurement model"]): add("sem","The research logic refers to SEM, latent constructs or a measurement/structural model.")
    if any(k in text for k in ["hierarchical regression","blockwise","incremental r2","incremental r-squared"]): add("hierarchical","The objective/design uses theory-driven predictor blocks.")
    if any(k in text for k in ["panel","fixed effect","random effect","country-year","firm-year","entity-year"]): add("panel","The design indicates repeated observations across entities and time.")
    if any(k in text for k in ["dcc-garch","dcc garch","dynamic conditional correlation"]): add("dcc_garch","The objective concerns time-varying cross-series correlations after volatility standardisation.")
    if any(k in text for k in ["garch","arch","volatility","conditional variance"]): add("volatility","The objective concerns time-varying conditional variance.")
    if any(k in text for k in ["vecm","vector error correction"]): add("vecm","The objective specifies a cointegrated multivariate error-correction system.")
    if any(k in text for k in ["johansen","engle-granger","cointegration"]): add("cointegration","The objective concerns non-stationary series and long-run equilibrium relationships.")
    if any(k in text for k in ["svar","structural var"]): add("svar","The research logic requires structurally identified shocks in a VAR system.")
    if any(k in text for k in ["tvp-var","tvp var","time-varying parameter var"]): add("tvp_var","The objective explicitly allows VAR coefficients to evolve through time.")
    if any(k in text for k in ["nardl","asymmetric","positive shock","negative shock"]): add("nardl","The objective concerns asymmetric positive and negative dynamic effects.")
    if any(k in text for k in ["ardl","bounds test","distributed lag"]): add("ardl","The research logic explicitly calls for ARDL/distributed-lag modelling or bounds testing.")
    if any(k in text for k in ["dols","dynamic ols"]): add("dols","The research logic calls for a cointegrating Dynamic OLS regression.")
    if any(k in text for k in ["decomposition","seasonal decomposition","stl","x-12","x12","x-13","x13"]): add("decomposition","The objective requires trend, seasonal and irregular decomposition.")
    if any(k in text for k in ["wavelet","dwt","modwt"]): add("wavelet","The objective includes time-localised frequency decomposition.")
    if any(k in text for k in ["emd","eemd","ceemdan","intrinsic mode"]): add("emd","The objective calls for adaptive empirical-mode decomposition.")
    if any(k in text for k in ["patchtst","informer","autoformer","n-beats","nbeats","n-hits","nhits","deepar","autoencoder","vae","cae"]): add("deep_forecasting","The research logic explicitly requests a deep time-series architecture.")
    if any(k in text for k in ["timesfm","chronos","timegpt","zero-shot"]): add("foundation_forecasting","The objective explicitly requests a foundation/zero-shot time-series model.")
    if any(k in text for k in ["prophet","neuralprophet"]): add("hybrid_forecasting","The objective explicitly requests Prophet/NeuralProphet-style trend-seasonality modelling.")
    if any(k in text for k in ["xgboost","lightgbm","catboost","gradient boosting","machine learning forecast","random forest forecast"]): add("ml_forecasting","The research logic explicitly requests machine-learning forecasting.")
    if any(k in text for k in ["time series","forecast","arima","sarima","arma","autoregressive","moving average"," var "]): add("time_series","The objectives/design indicate ordered temporal observations or forecasting.")
    if any(k in text for k in ["quantile","median regression","distributional effect"]): add("quantile_regression","The objective concerns conditional quantiles rather than only the conditional mean.")
    if any(k in text for k in ["binary logit","logistic regression"]): add("logistic","The outcome/logic calls for binary logistic modelling, subject to outcome coding.")
    if any(k in text for k in ["ordinal logit","ordinal regression"]): add("ordinal","The outcome/logic calls for an ordered-category model.")
    if any(k in text for k in ["multinomial","nominal outcome"]): add("multinomial","The outcome/logic calls for a nominal multi-category model.")
    if any(k in text for k in ["poisson","count outcome","negative binomial","overdispersion"]): add("negative_binomial" if "negative binomial" in text or "overdispersion" in text else "poisson","The objective concerns a count outcome; verify dispersion before choosing the final count model.")
    if any(k in text for k in ["effect","relationship","influence","predict","determinant","association"]): add("clrm","A linear regression family may be appropriate after confirming outcome type, design and assumptions.")
    if not recommendations: add("descriptives","Start with data quality and descriptive statistics before selecting an inferential model.")
    return recommendations

def objective_alignment(result: dict[str, Any], objective: str, hypothesis: str = "") -> dict[str, Any]:
    at=str(result.get("analysis") or "")
    return {"objective":str(objective or "").strip(),"hypothesis":str(hypothesis or "").strip(),"analysis_type":at,"covered":bool(str(objective or "").strip()),"note":"The result was generated from the uploaded dataset. Interpret only the coefficients/statistics returned by the calculation engine and keep causal language consistent with the approved design."}


def consistency_checks(result: dict[str, Any]) -> list[dict[str, Any]]:
    checks=[]; analysis=str(result.get("analysis") or "")
    for row in result.get("parameters") or []:
        b=row.get("coefficient"); p=row.get("pvalue"); lo=row.get("ci_low"); hi=row.get("ci_high")
        if b is not None and lo is not None and hi is not None and not (lo <= b <= hi): checks.append({"status":"error","message":f"{row.get('term')}: coefficient falls outside its reported confidence interval."})
        if p is not None and lo is not None and hi is not None:
            excludes_zero=(lo>0 or hi<0)
            if p < .05 and not excludes_zero: checks.append({"status":"warning","message":f"{row.get('term')}: p < .05 but the reported 95% CI includes zero. Review calculation/settings."})
            if p >= .05 and excludes_zero: checks.append({"status":"warning","message":f"{row.get('term')}: p >= .05 but the reported 95% CI excludes zero. Review calculation/settings."})
    if analysis=="mediation":
        e=result.get("effects") or {}; lo=e.get("bootstrap_ci_low"); hi=e.get("bootstrap_ci_high")
        checks.append({"status":"pass" if lo is not None and hi is not None and (lo>0 or hi<0) else "warning","message":"Indirect effect bootstrap interval excludes zero." if lo is not None and hi is not None and (lo>0 or hi<0) else "The bootstrap 95% interval for the indirect effect includes zero or is unavailable."})
    if analysis=="t_test":
        lev=((result.get("diagnostics") or {}).get("levene") or {}).get("pvalue")
        if result.get("variant")=="independent_student" and lev is not None and lev<.05: checks.append({"status":"warning","message":"Student independent t-test was requested but Levene's test indicates unequal variances at the 5% level. Consider Welch's t-test."})
    if analysis=="anova":
        lev=((result.get("diagnostics") or {}).get("levene") or {}).get("pvalue")
        if result.get("variant") not in {"welch","welch_anova"} and lev is not None and lev<.05: checks.append({"status":"warning","message":"ANOVA homogeneity-of-variance diagnostic is significant. Consider Welch ANOVA or a robust alternative where appropriate."})
    if analysis=="ancova":
        slope=((result.get("diagnostics") or {}).get("homogeneity_of_regression_slopes") or [])
        for item in slope:
            if item.get("pvalue") is not None and item.get("pvalue")<.05: checks.append({"status":"warning","message":"ANCOVA group-by-covariate interaction test suggests non-homogeneous regression slopes. Standard ANCOVA interpretation needs revision."})
    if analysis in {"poisson","negative_binomial","negbin"}:
        disp=((result.get("diagnostics") or {}).get("pearson_dispersion"))
        if analysis=="poisson" and disp is not None and disp>1.5: checks.append({"status":"warning","message":f"Poisson Pearson dispersion is {disp:.2f}; assess overdispersion and consider Negative Binomial/robust alternatives."})
    if analysis=="volatility":
        persistence=((result.get("model") or {}).get("persistence"))
        if persistence is not None and persistence>=1: checks.append({"status":"warning","message":f"Estimated volatility persistence is {persistence:.3f}, which is at or above one. Review stationarity/persistence and model specification."})
    if analysis=="dcc_garch":
        dcc=result.get("dcc_parameters") or {}; a=dcc.get("alpha"); b=dcc.get("beta")
        if a is not None and b is not None and a+b>=1: checks.append({"status":"warning","message":"DCC alpha + beta is at or above one; dynamic-correlation stationarity requires review."})
    if analysis in {"time_series","svar"}:
        diag=result.get("diagnostics") or {}
        if diag.get("stable") is False: checks.append({"status":"warning","message":"The fitted VAR/SVAR system is not stable under the reported root diagnostic."})
        lb=(diag.get("ljung_box") or diag.get("whiteness") or {}).get("pvalue") if isinstance(diag.get("ljung_box") or diag.get("whiteness"),dict) else None
        if lb is not None and lb<.05: checks.append({"status":"warning","message":"Residual autocorrelation/whiteness diagnostic is significant; dynamic specification may be inadequate."})
    if analysis=="vecm":
        p=((result.get("diagnostics") or {}).get("whiteness") or {}).get("pvalue")
        if p is not None and p<.05: checks.append({"status":"warning","message":"VECM residual whiteness test is significant. Consider lag/deterministic specification review."})
    if analysis=="wavelet":
        rmse=((result.get("diagnostics") or {}).get("reconstruction_rmse"))
        if rmse is not None and rmse>1e-6: checks.append({"status":"warning","message":f"Wavelet reconstruction RMSE is {rmse:.6g}; inspect boundary/level settings before interpreting decomposed components."})
    if analysis in {"advanced_forecasting_adapter"} and result.get("runtime_available") is False:
        checks.append({"status":"warning","message":"The requested specialist forecasting runtime is not active. ProjectReady did not substitute another model."})
    if not checks: checks.append({"status":"pass","message":"No deterministic internal contradiction was detected in the returned statistics. Substantive and design-level review is still required."})
    return checks


def result_interpretation(result: dict[str, Any]) -> list[str]:
    """Restrained prose derived only from deterministic/verified result fields."""
    notes=[]; alpha=.05; analysis=str(result.get("analysis") or "")
    params=result.get("parameters") if isinstance(result.get("parameters"),list) else []
    substantive=[r for r in params if str(r.get("term") or "").lower() not in {"const","intercept"} and not str(r.get("term") or "").startswith(("entity_","time_"))]
    for row in substantive[:30]:
        b=row.get("coefficient"); p=row.get("pvalue"); term=str(row.get("term") or "predictor")
        if b is None: continue
        direction="positive" if float(b)>0 else "negative" if float(b)<0 else "zero"
        if p is not None:
            sig="statistically significant at the 5% level" if float(p)<alpha else "not statistically significant at the 5% level"
            notes.append(f"{term} has a {direction} estimated coefficient ({float(b):.3f}) and is {sig} (p {('< .001' if float(p)<.001 else '= %.3f' % float(p))}).")
        else: notes.append(f"{term} has a {direction} estimated coefficient of {float(b):.3f}; no p-value is available in this result row.")
    if analysis=="t_test":
        t=result.get("test") or {}; notes.append(f"The {str(result.get('variant') or '').replace('_',' ')} t-test returned t={float(t.get('t')):.3f}, df={float(t.get('df')):.2f}, p={float(t.get('pvalue')):.3f}." if all(t.get(k) is not None for k in ['t','df','pvalue']) else "The t-test result is reported with its group/reference comparison and diagnostics.")
    if analysis=="anova":
        t=result.get("test") or {}; p=t.get("pvalue")
        if p is not None: notes.append(f"The omnibus ANOVA test is {'statistically significant' if p<.05 else 'not statistically significant'} at the 5% level (p={p:.3f}). Post-hoc comparisons should be interpreted only when justified by the omnibus result and design.")
        eta=(result.get("effect_size") or {}).get("eta_squared")
        if eta is not None: notes.append(f"The reported eta-squared effect-size estimate is {eta:.3f}; interpret its substantive magnitude in the study context rather than by a mechanical label alone.")
    if analysis=="manova":
        tests=result.get("multivariate_tests") or []
        pillai=next((x for x in tests if str(x.get('statistic_name') or '').lower().startswith('pillai')),None)
        if pillai and pillai.get("pvalue") is not None: notes.append(f"The reported Pillai multivariate test has p={pillai['pvalue']:.3f}. Interpret the multivariate result before any follow-up univariate analyses.")
    if analysis=="mediation":
        e=result.get("effects") or {}; ind=e.get("indirect"); lo=e.get("bootstrap_ci_low"); hi=e.get("bootstrap_ci_high")
        if ind is not None and lo is not None and hi is not None: notes.append(f"The estimated indirect effect is {float(ind):.3f}, with a bootstrap 95% interval from {float(lo):.3f} to {float(hi):.3f}. The interval {'does not include' if (float(lo)>0 or float(hi)<0) else 'includes'} zero.")
    if analysis=="moderated_mediation":
        for item in result.get("conditional_indirect_effects") or []:
            if item.get("conditional_indirect_effect") is not None: notes.append(f"At {item.get('level')}, the estimated conditional indirect effect is {float(item['conditional_indirect_effect']):.3f}.")
    if analysis=="sem":
        fit=result.get("fit") or {}; bits=[]
        for key in ["CFI","TLI","RMSEA","SRMR"]:
            if fit.get(key) is not None: bits.append(f"{key}={float(fit[key]):.3f}")
        if bits: notes.append("SEM fit statistics reported by the fitted model are " + ", ".join(bits) + ". Evaluate the measurement and structural models against pre-specified criteria rather than using one cutoff mechanically.")
    if analysis=="panel_regression": notes.append(f"The panel estimator uses {result.get('entities')} entities across {result.get('periods')} observed time periods. Interpretation should respect within-entity/repeated-observation structure and the selected {result.get('model_type')} estimator.")
    if analysis=="time_series": notes.append("Stationarity, information criteria, stability/root and residual-whiteness diagnostics are reported separately. Dynamic or forecasting claims should be made only after the selected specification is judged adequate.")
    if analysis=="dols": notes.append("DOLS estimates the long-run level relationship while including leads/lags of first differences and HAC inference. Interpret it as a cointegrating-regression result only after the integration/cointegration evidence is defensible.")
    if analysis=="ardl":
        bt=(result.get("bounds_test") or {}).get("statistic")
        if bt is not None: notes.append(f"The ARDL/UECM bounds-test statistic is {float(bt):.3f}. Compare it with the reported case-specific critical bounds and the I(0)/I(1) restrictions before concluding cointegration.")
    if analysis=="nardl":
        for w in result.get("asymmetry_tests") or []:
            if w.get("pvalue") is not None: notes.append(f"The {w.get('test')} asymmetry test returned p={float(w['pvalue']):.3f}.")
    if analysis=="cointegration": notes.append("Cointegration evidence should be read jointly with the per-series integration diagnostics and the selected deterministic/lag specification; a test result is not itself a structural causal model.")
    if analysis=="vecm": notes.append(f"The VECM uses cointegration rank {result.get('coint_rank')} and reports adjustment coefficients and cointegrating vectors separately from short-run dynamics.")
    if analysis=="svar": notes.append(f"SVAR identification is reported as {result.get('identification') or result.get('svar_type')}. Structural-shock interpretation is valid only if the identifying restrictions are theoretically justified and the reduced-form system is stable.")
    if analysis=="volatility":
        pers=(result.get("model") or {}).get("persistence")
        if pers is not None: notes.append(f"Estimated ARCH/GARCH variance persistence is {float(pers):.3f}; residual and squared-residual diagnostics should be checked before using the volatility path substantively.")
    if analysis=="dcc_garch":
        d=result.get("dcc_parameters") or {}
        if d.get("alpha") is not None and d.get("beta") is not None: notes.append(f"The fitted DCC parameters are alpha={float(d['alpha']):.3f} and beta={float(d['beta']):.3f}; dynamic-correlation interpretation should consider persistence and convergence.")
    if analysis=="network":
        n=result.get("network") or {}; notes.append(f"The network contains {n.get('nodes')} nodes and {n.get('edges')} edges with density {float(n.get('density')):.3f}. Centrality and community measures describe the supplied tie definition and should not be interpreted independently of how edges were constructed." if n.get('density') is not None else "Network measures describe the supplied node/tie construction and must be interpreted in that substantive context.")
    if analysis=="ml_forecasting":
        m=result.get("metrics") or {}; notes.append(f"The chronological holdout produced MAE={float(m.get('mae')):.3f} and RMSE={float(m.get('rmse')):.3f}. Compare these with naive and statistical baselines using rolling-origin validation before claiming predictive superiority." if m.get('mae') is not None and m.get('rmse') is not None else "Machine-learning forecast performance is reported on a chronological holdout; add baseline and rolling-origin comparisons before publication claims.")
    if analysis=="deep_autoencoder": notes.append("Autoencoder outputs are reconstruction/anomaly diagnostics only. Reconstructed or synthetic values are model outputs and are not treated as observed research data.")
    if analysis in {"advanced_forecasting_adapter","foundation_forecasting","deep_forecasting","hybrid_forecasting"} and result.get("runtime_available") is False: notes.append(str(result.get("message") or "The exact specialist runtime is not configured, so no substitute model was run."))
    if analysis=="wavelet": notes.append("Wavelet components are scale-localised signal representations. Check reconstruction error, boundary treatment and sensitivity to wavelet family/level before substantive interpretation.")
    if analysis=="emd": notes.append("IMFs are adaptive data-driven components. Inspect reconstruction, mode mixing and substantive frequency meaning rather than treating every IMF as a distinct real-world process.")
    return notes

def chapter_four_result_block(result: dict[str, Any]) -> str:
    align=result.get("objective_alignment") or {}; objective=str(align.get("objective") or "Unmapped objective")
    lines=[f"### Result for: {objective}","",f"Analysis: {str(result.get('analysis') or '').replace('_',' ').title()}"]
    if result.get("n") is not None: lines.append(f"Usable observations: {int(result['n'])}")
    lines.append("")
    for note in result_interpretation(result): lines.append(note)
    checks=result.get("consistency_checks") or []
    warnings=[str(c.get("message") or "") for c in checks if str(c.get("status") or "") in {"warning","error"}]
    if warnings:
        lines.extend(["","Statistical consistency items requiring review:"]+[f"- {w}" for w in warnings])
    lines.extend(["","Interpretation boundary: These statements are generated only from the verified calculation output. Causal wording must match the approved design, and substantive conclusions remain the researcher's responsibility."])
    return "\n".join(lines)


def run_analysis(project_id: str, dataset_id: str, spec: dict[str, Any], objectives: list[str] | None = None) -> dict[str, Any]:
    df,_=load_dataset(project_id,dataset_id)
    kind=str(spec.get("analysis_type") or "descriptives").strip().lower()
    if kind in {"quality","data_quality"}: result={"analysis":"data_quality","quality":data_quality(df)}
    elif kind in {"descriptive","descriptives"}: result={"analysis":"descriptives","descriptives":descriptive_statistics(df),"quality":data_quality(df)}
    elif kind=="reliability": result={"analysis":"reliability","reliability":cronbach_alpha(df,list(spec.get("items") or []))}
    elif kind in {"ols","clrm"}: result=run_ols(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),bool(spec.get("robust"))); result["analysis"]="clrm" if kind=="clrm" else "ols"
    elif kind=="hierarchical": result=run_hierarchical_ols(df,str(spec.get("dependent") or ""),list(spec.get("blocks") or []))
    elif kind in {"logistic","poisson","negative_binomial","negbin"}: result=run_glm(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),kind)
    elif kind=="ordinal": result=run_ordinal(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []))
    elif kind=="multinomial": result=run_multinomial(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []))
    elif kind=="multilevel": result=run_multilevel(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),str(spec.get("group") or ""))
    elif kind=="mediation": result=run_mediation(df,str(spec.get("x") or ""),str(spec.get("mediator") or ""),str(spec.get("y") or ""),list(spec.get("covariates") or []),int(spec.get("bootstrap") or 1000))
    elif kind=="moderation": result=run_moderation(df,str(spec.get("x") or ""),str(spec.get("moderator") or ""),str(spec.get("y") or ""),list(spec.get("covariates") or []),bool(spec.get("center",True)))
    elif kind=="moderated_mediation": result=run_moderated_mediation(df,str(spec.get("x") or ""),str(spec.get("mediator") or ""),str(spec.get("moderator") or ""),str(spec.get("y") or ""),list(spec.get("covariates") or []),int(spec.get("bootstrap") or 1000))
    elif kind=="t_test": result=run_t_test(df,str(spec.get("dependent") or ""),str(spec.get("variant") or "independent_welch"),str(spec.get("group") or ""),str(spec.get("group_a") or ""),str(spec.get("group_b") or ""),float(spec.get("reference") or 0),str(spec.get("paired_with") or ""))
    elif kind=="anova": result=run_anova(df,str(spec.get("dependent") or ""),str(spec.get("group") or ""),str(spec.get("variant") or "one_way"),str(spec.get("factor2") or ""))
    elif kind=="ancova": result=run_ancova(df,str(spec.get("dependent") or ""),str(spec.get("group") or ""),list(spec.get("covariates") or spec.get("predictors") or []),str(spec.get("factor2") or ""),bool(spec.get("robust")))
    elif kind=="manova": result=run_manova(df,list(spec.get("outcomes") or []),list(spec.get("predictors") or []),list(spec.get("categorical") or []))
    elif kind=="quantile_regression": result=run_quantile(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),list(spec.get("quantiles") or [.25,.5,.75]))
    elif kind=="dols": result=run_dols(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),str(spec.get("time_variable") or ""),int(spec.get("leads") or 1),int(spec.get("lags") or 1),bool(spec.get("trend")))
    elif kind=="ardl": result=run_ardl(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),str(spec.get("time_variable") or ""),int(spec.get("ar_lags") or 1),int(spec.get("dl_lags") or 1),str(spec.get("trend") or "c"),int(spec.get("bounds_case") or 3))
    elif kind=="nardl": result=run_nardl(df,str(spec.get("dependent") or ""),str(spec.get("regressor") or ((spec.get("predictors") or [""])[0])),str(spec.get("time_variable") or ""),int(spec.get("p") or 1),int(spec.get("q") or 1))
    elif kind=="decomposition": result=run_decomposition(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),str(spec.get("method") or "stl"),int(spec.get("period") or 12),bool(spec.get("robust",True)))
    elif kind=="cointegration": result=run_cointegration(df,list(spec.get("variables") or ([spec.get("dependent")] if spec.get("dependent") else []) + list(spec.get("predictors") or [])),str(spec.get("time_variable") or ""),str(spec.get("method") or "johansen"),int(spec.get("det_order") or 0),int(spec.get("k_ar_diff") or 1))
    elif kind=="vecm": result=run_vecm(df,list(spec.get("variables") or ([spec.get("dependent")] if spec.get("dependent") else []) + list(spec.get("predictors") or [])),str(spec.get("time_variable") or ""),int(spec.get("coint_rank") or 1),int(spec.get("k_ar_diff") or 1),str(spec.get("deterministic") or "ci"))
    elif kind=="svar": result=run_svar(df,list(spec.get("variables") or ([spec.get("dependent")] if spec.get("dependent") else []) + list(spec.get("predictors") or [])),str(spec.get("time_variable") or ""),int(spec.get("lags") or 1),str(spec.get("svar_type") or "A"),spec.get("A"),spec.get("B"))
    elif kind=="tvp_var": result=run_tvp_var(df,list(spec.get("variables") or ([spec.get("dependent")] if spec.get("dependent") else []) + list(spec.get("predictors") or [])),str(spec.get("time_variable") or ""),int(spec.get("lags") or 1),float(spec.get("forgetting_factor") or .98))
    elif kind in {"volatility","arch","garch","gjr_garch","egarch"}: result=run_volatility(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),str(spec.get("model_type") or (kind if kind!="volatility" else "garch")),int(spec.get("p") or 1),int(spec.get("q") or 1),int(spec.get("o") or 0),str(spec.get("distribution") or "normal"))
    elif kind=="dcc_garch": result=run_dcc_garch(df,list(spec.get("variables") or ([spec.get("dependent")] if spec.get("dependent") else []) + list(spec.get("predictors") or [])),str(spec.get("time_variable") or ""),int(spec.get("p") or 1),int(spec.get("q") or 1))
    elif kind=="network": result=run_network(df,str(spec.get("source") or ""),str(spec.get("target") or ""),str(spec.get("weight") or ""),bool(spec.get("directed")))
    elif kind=="wavelet": result=run_wavelet(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),str(spec.get("method") or "dwt"),str(spec.get("wavelet") or "db4"),int(spec.get("level") or 3))
    elif kind=="emd": result=run_emd(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),str(spec.get("method") or "emd"))
    elif kind=="ml_forecasting": result=run_ml_forecast(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),str(spec.get("model_type") or "gradient_boosting"),int(spec.get("lags") or 12),int(spec.get("horizon") or 1),float(spec.get("test_fraction") or .2))
    elif kind in {"deep_forecasting","foundation_forecasting","hybrid_forecasting","advanced_forecasting_adapter"}: result=run_advanced_forecasting_adapter(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),str(spec.get("model_type") or ""),int(spec.get("lags") or 24),int(spec.get("horizon") or 12),int(spec.get("epochs") or 120))
    elif kind in {"time_series","ar","ma","arma","arima","sarimax","var"}:
        model_type=str(spec.get("model_type") or (kind if kind!="time_series" else "arima")).lower()
        order=list(spec.get("order") or [1,0,0])
        if model_type=="ar": order=[int(spec.get("p") or order[0] or 1),0,0]; model_type="arima"
        elif model_type=="ma": order=[0,0,int(spec.get("q") or (order[2] if len(order)>2 else 1) or 1)]; model_type="arima"
        elif model_type=="arma": order=[int(spec.get("p") or order[0] or 1),0,int(spec.get("q") or (order[2] if len(order)>2 else 1) or 1)]; model_type="arima"
        result=run_time_series(df,str(spec.get("dependent") or ""),str(spec.get("time_variable") or ""),model_type,order,list(spec.get("seasonal_order") or [0,0,0,0]),list(spec.get("exogenous") or spec.get("predictors") or []),int(spec.get("lags") or 1))
    elif kind in {"panel","panel_regression"}: result=run_panel(df,str(spec.get("dependent") or ""),list(spec.get("predictors") or []),str(spec.get("entity") or ""),str(spec.get("time_variable") or ""),str(spec.get("model_type") or "fixed_effects"))
    elif kind=="sem": result=run_sem(df,str(spec.get("model_spec") or ""))
    else: raise ValueError("Unsupported analysis type.")
    objective=str(spec.get("objective") or "")
    result["objective_alignment"]=objective_alignment(result,objective,str(spec.get("hypothesis") or ""))
    result["consistency_checks"]=consistency_checks(result)
    result["interpretation"]=result_interpretation(result)
    result["chapter_four_block"]=chapter_four_result_block(result)
    # Every inferential/specialist result carries its declared assumptions, diagnostics and variants.
    guide_map = {
        "ols": "clrm", "clrm": "clrm",
        "panel_regression": "panel", "panel": "panel",
        "sem": "sem",
        "mediation": "mediation", "moderation": "moderation", "moderated_mediation": "moderated_mediation",
        "multilevel": "multilevel", "hierarchical": "hierarchical", "logistic": "logistic", "ordinal": "ordinal", "multinomial": "multinomial", "poisson": "count_glm", "negative_binomial": "count_glm", "negbin": "count_glm", "reliability": "reliability",
        "arch": "volatility", "garch": "volatility", "gjr_garch": "volatility", "egarch": "volatility", "dcc_garch": "volatility", "volatility": "volatility",
        "ar": "time_series", "ma": "time_series", "arma": "time_series", "arima": "time_series", "sarimax": "time_series", "var": "time_series", "time_series": "time_series",
    }
    catalog_key = guide_map.get(kind, kind)
    meta = METHOD_CATALOG.get(catalog_key)
    if meta:
        result["method_guidance"] = {"label": meta.get("label"), "category": meta.get("category"), "variants": meta.get("variants") or [], "assumptions": meta.get("assumptions") or [], "expected_diagnostics": meta.get("diagnostics") or []}
    run_id=str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute("INSERT INTO analysis_runs (id, project_id, dataset_id, analysis_type, specification_json, result_json) VALUES (?, ?, ?, ?, ?, ?)",(run_id,project_id,dataset_id,kind,json.dumps(spec),json.dumps(result)))
        conn.commit()
    result["run_id"]=run_id
    return result


def list_runs(project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows=conn.execute("SELECT id, dataset_id, analysis_type, specification_json, result_json, created_at FROM analysis_runs WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",(project_id,max(1,min(int(limit),100)))).fetchall()
    out=[]
    for row in rows:
        d=dict(row)
        for field in ["specification_json","result_json"]:
            try: d[field.replace("_json","")]=json.loads(d.pop(field) or "{}")
            except Exception: d[field.replace("_json","")]={}
        out.append(d)
    return out
