from __future__ import annotations

import importlib.util
import math
import os
from typing import Any


def _f(value: Any) -> float | None:
    try:
        out = float(value)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def _available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _assumption(name: str, rationale: str, diagnostic: str = "") -> dict[str, str]:
    return {"assumption": name, "why_it_matters": rationale, "diagnostic": diagnostic}


METHOD_CATALOG: dict[str, dict[str, Any]] = {
    "time_series": {
        "category": "Stationary & non-stationary time series",
        "label": "AR / MA / ARMA / ARIMA / SARIMAX / VAR",
        "variants": ["AR", "MA", "ARMA", "ARIMA", "seasonal ARIMA/SARIMAX", "VAR"],
        "assumptions": [
            _assumption("Temporal ordering and regular frequency are correctly specified", "Lag structures and seasonal interpretation depend on ordering and frequency.", "time-index/frequency check"),
            _assumption("Stationarity after required transformations", "ARMA/VAR dynamics are conventionally interpreted for stationary series; ARIMA uses differencing to address integration.", "ADF/KPSS and differencing review"),
            _assumption("Residual innovations are approximately white noise", "Remaining autocorrelation indicates misspecified dynamics.", "Ljung-Box / residual ACF"),
        ],
        "diagnostics": ["ADF", "KPSS", "AIC/BIC/HQIC", "Ljung-Box", "residual normality", "stability/invertibility roots", "forecast error metrics"],
    },
    "panel": {
        "category": "Panel-data econometrics",
        "label": "Panel-data regression",
        "variants": ["pooled OLS", "entity fixed effects", "time fixed effects", "two-way fixed effects", "random effects", "cluster-robust inference"],
        "assumptions": [
            _assumption("Repeated entity-time structure is valid", "Panel estimators rely on a correctly identified unit and time dimension.", "duplicate entity-time and balance checks"),
            _assumption("Strict/sequential exogeneity appropriate to estimator", "Unobserved time-varying confounding can invalidate coefficient interpretation.", "design review; lag/endogeneity sensitivity"),
            _assumption("FE/RE choice matches correlation of unit effects with regressors", "Random effects imposes a stronger orthogonality assumption than fixed effects.", "Hausman-style comparison where estimable"),
        ],
        "diagnostics": ["panel balance", "within/between variation", "cluster-robust SE", "serial correlation warning", "cross-sectional dependence warning", "FE/RE comparison"],
    },
    "sem": {
        "category": "Latent-variable / path modelling",
        "label": "Structural Equation Modelling (SEM)",
        "variants": ["path analysis", "CFA measurement model", "full latent SEM", "mediation paths", "multi-group/measurement-invariance planning"],
        "assumptions": [
            _assumption("Model is identified and theory-driven", "SEM cannot rescue an underidentified or arbitrary path specification.", "degrees of freedom / identification review"),
            _assumption("Measurement quality is adequate for latent constructs", "Structural paths are only as credible as the measurement model.", "loadings, reliability, convergent/discriminant validity"),
            _assumption("Distribution/estimator assumptions are appropriate", "Maximum-likelihood SEM can be sensitive to non-normality and categorical indicators.", "normality and estimator-selection review"),
        ],
        "diagnostics": ["CFI", "TLI", "RMSEA", "SRMR", "chi-square", "factor loadings", "residuals/modification diagnostics with theory safeguards", "professional path diagram"],
    },
    "mediation": {
        "category": "Conditional process analysis",
        "label": "Mediation",
        "variants": ["simple mediation", "parallel/serial mediation planning", "bootstrap indirect effect"],
        "assumptions": [_assumption("Temporal/causal ordering is theoretically justified", "A statistical indirect effect is not by itself proof of causal mediation.", "design and timing review"), _assumption("Regression-model assumptions are adequate", "Path estimates inherit the assumptions of their component regressions.", "residual, collinearity and influence diagnostics")],
        "diagnostics": ["a/b/direct/total effects", "bootstrap CI", "component-model diagnostics", "sensitivity to covariates"],
    },
    "moderation": {
        "category": "Conditional process analysis",
        "label": "Moderation",
        "variants": ["continuous × continuous", "categorical moderator", "simple slopes", "Johnson-Neyman planning"],
        "assumptions": [_assumption("Interaction is correctly specified", "Main effects alone do not test moderation.", "interaction term and functional-form review"), _assumption("Adequate support across moderator range", "Simple slopes in sparse regions are unstable.", "range/cell-size review")],
        "diagnostics": ["interaction coefficient", "simple slopes", "VIF", "residual diagnostics", "conditional-effect plot"],
    },
    "multilevel": {
        "category": "Multilevel / hierarchical modelling",
        "label": "Multilevel model",
        "variants": ["random intercept", "random slope planning", "cross-level interaction planning"],
        "assumptions": [_assumption("Meaningful clustering", "Multilevel modelling requires nested/grouped dependence.", "ICC and cluster-size review"), _assumption("Random-effect distribution/model is adequate", "Incorrect random structure can distort standard errors and inferences.", "variance components and residual review")],
        "diagnostics": ["ICC", "group counts", "random-effect variance", "residual diagnostics", "convergence"],
    },

    "hierarchical": {
        "category": "Traditional econometric & linear regression",
        "label": "Hierarchical / blockwise multiple regression",
        "variants": ["theory-driven block entry", "incremental R-squared", "robust-SE sensitivity"],
        "assumptions": [
            _assumption("Linear conditional mean and correctly specified blocks", "Incremental explanatory contribution is meaningful only when variables are entered in a defensible order.", "RESET / residual plots / block rationale"),
            _assumption("Independent, homoskedastic errors unless robust inference is used", "Conventional OLS standard errors depend on error assumptions.", "Breusch-Pagan/White, Durbin-Watson/Breusch-Godfrey"),
            _assumption("No harmful multicollinearity", "Severe collinearity destabilises block coefficients and change tests.", "VIF/condition review"),
        ],
        "diagnostics": ["R-squared and adjusted R-squared", "change in R-squared", "nested F/change test", "VIF", "Breusch-Pagan", "White", "Breusch-Godfrey", "RESET", "Cook's distance"],
    },
    "logistic": {
        "category": "Generalised linear models",
        "label": "Binary logistic regression",
        "variants": ["binary logit", "odds-ratio reporting", "robust covariance sensitivity"],
        "assumptions": [
            _assumption("Binary outcome is correctly coded", "The Bernoulli likelihood requires two outcome states.", "outcome-level check"),
            _assumption("Continuous predictors are approximately linear in the logit", "Logit non-linearity can bias effect estimates.", "Box-Tidwell/spline sensitivity planning"),
            _assumption("No quasi/perfect separation and no harmful multicollinearity", "Separation produces unstable or infinite estimates.", "cell counts, convergence, VIF"),
        ],
        "diagnostics": ["convergence", "odds ratios and confidence intervals", "likelihood/AIC/BIC", "classification/discrimination where appropriate", "influence", "VIF", "linearity-in-logit review"],
    },
    "ordinal": {
        "category": "Generalised linear models",
        "label": "Ordinal logistic regression",
        "variants": ["ordered logit", "ordered probit planning", "partial proportional-odds planning"],
        "assumptions": [
            _assumption("Outcome categories have a defensible order", "Ordinal models exploit rank ordering without assuming equal spacing.", "category/order review"),
            _assumption("Proportional-odds/parallel-lines assumption for ordered logit", "A common slope across cut-points is a core restriction.", "parallel-lines sensitivity/test where available"),
        ],
        "diagnostics": ["threshold estimates", "AIC/BIC", "convergence", "parallel-lines/proportional-odds review", "sparse-category warning", "VIF"],
    },
    "multinomial": {
        "category": "Generalised linear models",
        "label": "Multinomial logistic regression",
        "variants": ["baseline-category multinomial logit", "relative-risk/odds interpretation"],
        "assumptions": [
            _assumption("Outcome categories are nominal and mutually exclusive", "Multinomial logit models unordered alternatives.", "category coding review"),
            _assumption("Independence of irrelevant alternatives is substantively plausible", "IIA can be restrictive when alternatives are close substitutes.", "research-design and alternative-model sensitivity"),
        ],
        "diagnostics": ["convergence", "AIC/BIC", "category counts", "coefficient/relative-risk intervals", "IIA sensitivity", "VIF"],
    },
    "count_glm": {
        "category": "Generalised linear models",
        "label": "Poisson / Negative Binomial regression",
        "variants": ["Poisson", "Negative Binomial", "robust-SE sensitivity", "zero-inflation planning"],
        "assumptions": [
            _assumption("Outcome is a non-negative count", "Count likelihoods are not appropriate for arbitrary continuous outcomes.", "range/integer check"),
            _assumption("Poisson equidispersion or an appropriate overdispersion alternative", "Overdispersion can make Poisson inference anticonservative.", "mean-variance/dispersion review"),
            _assumption("Independent observations conditional on predictors", "Unmodelled clustering invalidates standard errors.", "design/cluster review"),
        ],
        "diagnostics": ["deviance/Pearson dispersion", "AIC/BIC", "incidence-rate ratios", "zero-frequency review", "residuals", "influence", "overdispersion"],
    },
    "moderated_mediation": {
        "category": "Conditional process analysis",
        "label": "Moderated mediation / conditional indirect effects",
        "variants": ["first-stage moderation", "second-stage moderation", "direct-effect moderation", "conditional indirect effects"],
        "assumptions": [
            _assumption("The moderated path is specified a priori", "Conditional process models are easy to overfit when moderators are moved post hoc.", "conceptual-framework/research-logic review"),
            _assumption("Component regression assumptions and support across moderator values are adequate", "Conditional indirect effects inherit component-model limitations.", "residual, VIF, range/cell-size diagnostics"),
        ],
        "diagnostics": ["interaction terms", "conditional indirect effects", "bootstrap confidence intervals", "simple slopes", "VIF", "component-model residual diagnostics"],
    },
    "reliability": {
        "category": "Measurement diagnostics",
        "label": "Internal consistency / reliability diagnostics",
        "variants": ["Cronbach alpha", "item-total diagnostics planning", "omega/SEM reliability planning"],
        "assumptions": [
            _assumption("Items are intended to measure a common construct", "Alpha is not evidence of unidimensionality by itself.", "construct/item mapping and factor-structure review"),
            _assumption("Item coding is directionally consistent", "Unreversed negatively keyed items can depress reliability.", "item correlation and coding review"),
        ],
        "diagnostics": ["Cronbach alpha", "item count", "missingness", "item-total/correlation review", "factor-structure follow-up where appropriate"],
    },
    "t_test": {
        "category": "Mean comparison",
        "label": "t-tests",
        "variants": ["one-sample", "independent Student", "independent Welch", "paired"],
        "assumptions": [
            _assumption("Independent observations", "Required for independent-group inference.", "Study design and duplicate/cluster review"),
            _assumption("Approximately normal outcome within groups", "Especially relevant in small samples.", "Shapiro-Wilk and Q-Q/residual review"),
            _assumption("Equal variances for Student t-test", "Student's pooled-variance t-test uses this restriction.", "Levene test; use Welch when violated"),
        ],
        "diagnostics": ["Shapiro-Wilk", "Levene variance test", "sample size", "Cohen's d / paired dz", "confidence interval"],
    },
    "anova": {
        "category": "Mean comparison",
        "label": "ANOVA",
        "variants": ["one-way ANOVA", "Welch ANOVA", "factorial ANOVA", "Tukey HSD post-hoc"],
        "assumptions": [
            _assumption("Independent observations", "ANOVA assumes independent errors.", "Design review"),
            _assumption("Normal residuals", "F inference is based on approximately normal errors.", "Shapiro-Wilk / Jarque-Bera on residuals"),
            _assumption("Homogeneity of variance", "Classical ANOVA assumes common group variance.", "Levene; Welch ANOVA alternative"),
        ],
        "diagnostics": ["Levene", "residual normality", "eta-squared", "omega-squared", "Tukey HSD"],
    },
    "ancova": {
        "category": "Mean comparison",
        "label": "ANCOVA",
        "variants": ["one-factor ANCOVA", "multi-factor ANCOVA", "robust-covariance ANCOVA"],
        "assumptions": [
            _assumption("Linear covariate-outcome relation", "ANCOVA adjusts linearly for covariates.", "Residual/partial-residual review"),
            _assumption("Homogeneity of regression slopes", "Group-by-covariate interactions should be checked before a common adjusted slope is assumed.", "Group × covariate interaction test"),
            _assumption("Independent, homoskedastic residuals", "Needed for conventional F tests.", "Breusch-Pagan / robust covariance option"),
        ],
        "diagnostics": ["slope-homogeneity interaction", "VIF", "Breusch-Pagan", "residual normality", "adjusted means"],
    },
    "manova": {
        "category": "Mean comparison",
        "label": "MANOVA",
        "variants": ["one-way MANOVA", "factorial MANOVA", "MANCOVA-style multivariate model"],
        "assumptions": [
            _assumption("Independent observations", "Multivariate test statistics assume independent rows.", "Design review"),
            _assumption("Multivariate normality", "Classical MANOVA is sensitive in small/unbalanced samples.", "Univariate residual checks plus multivariate outlier review"),
            _assumption("Homogeneity of covariance matrices", "Group covariance structures should be reasonably comparable.", "Group covariance review / Box-M style warning"),
        ],
        "diagnostics": ["Wilks' lambda", "Pillai trace", "Hotelling-Lawley trace", "Roy maximum root", "group covariance review"],
    },
    "clrm": {
        "category": "Traditional econometric & linear regression",
        "label": "Classical Linear Regression Model (CLRM)",
        "variants": ["OLS", "HC3 robust OLS", "cluster-robust OLS"],
        "assumptions": [
            _assumption("Linearity / correct functional form", "The conditional mean should be adequately specified.", "Ramsey RESET and residual plots"),
            _assumption("No perfect multicollinearity", "Parameters cannot be uniquely estimated under exact collinearity.", "VIF / matrix rank"),
            _assumption("Zero conditional mean / exogeneity", "Needed for unbiased/consistent causal coefficient interpretation.", "Design and endogeneity review; not established by a residual test alone"),
            _assumption("Homoskedasticity for classical SEs", "Gauss-Markov efficiency and conventional SEs rely on constant conditional variance.", "Breusch-Pagan / White; robust SE option"),
            _assumption("No serial correlation when observations are ordered", "Serial dependence invalidates conventional standard errors.", "Durbin-Watson / Breusch-Godfrey"),
            _assumption("Normal residuals for small-sample exact tests", "Large-sample inference is less dependent on residual normality.", "Jarque-Bera"),
        ],
        "diagnostics": ["VIF", "Breusch-Pagan", "White", "Breusch-Godfrey", "Durbin-Watson", "Jarque-Bera", "RESET", "Cook's distance", "leverage"],
    },
    "quantile_regression": {
        "category": "Traditional econometric & linear regression",
        "label": "Quantile Regression",
        "variants": ["median regression", "multiple quantiles", "heterogeneous-effect profile"],
        "assumptions": [
            _assumption("Independent/appropriately dependent observations", "Inference must match the sampling structure.", "Design review"),
            _assumption("Conditional quantile specification is meaningful", "Coefficients describe the selected conditional quantile, not a mean effect.", "Compare estimates across quantiles"),
        ],
        "diagnostics": ["pseudo R-squared", "quantile coefficient comparison", "bootstrap/asymptotic confidence intervals"],
    },
    "dols": {
        "category": "Traditional econometric & linear regression",
        "label": "Dynamic OLS (DOLS)",
        "variants": ["single-regressor DOLS", "multivariate DOLS", "trend-augmented DOLS"],
        "assumptions": [
            _assumption("Variables are integrated/cointegrated as intended", "DOLS is a long-run cointegrating regression, not a generic OLS substitute.", "ADF/KPSS and Engle-Granger/Johansen evidence"),
            _assumption("Lead/lag order adequately absorbs short-run endogeneity and serial correlation", "Misspecified dynamics can bias long-run inference.", "Residual serial-correlation tests and sensitivity to lead/lag order"),
        ],
        "diagnostics": ["ADF/KPSS", "Engle-Granger cointegration", "Breusch-Godfrey", "Newey-West/HAC inference", "lead-lag sensitivity"],
    },
    "ardl": {
        "category": "Traditional econometric & linear regression",
        "label": "ARDL / Bounds Test",
        "variants": ["ARDL", "UECM", "Pesaran-Shin-Smith bounds test", "lag-order comparison"],
        "assumptions": [
            _assumption("No variable is I(2) for bounds-testing interpretation", "ARDL bounds critical values are not designed for I(2) variables.", "ADF/KPSS integration-order screening"),
            _assumption("Stable dynamic specification", "Lag order and deterministic terms affect both short- and long-run estimates.", "AIC/BIC, roots/stability, residual diagnostics"),
            _assumption("Serially well-behaved residuals", "Residual autocorrelation undermines dynamic inference.", "ARDL serial-correlation test"),
        ],
        "diagnostics": ["ADF/KPSS", "bounds test", "serial correlation", "ARCH-LM heteroskedasticity", "normality", "AIC/BIC/HQIC", "stability"],
    },
    "nardl": {
        "category": "Traditional econometric & linear regression",
        "label": "Nonlinear ARDL (NARDL)",
        "variants": ["positive/negative partial-sum decomposition", "short-run asymmetry", "long-run asymmetry"],
        "assumptions": [
            _assumption("No I(2) variables for ARDL-style cointegration logic", "NARDL inherits the integration-order restriction of the ARDL bounds framework.", "ADF/KPSS"),
            _assumption("Asymmetric decomposition is theoretically justified", "Positive and negative shocks should have substantive meaning.", "Research logic and Wald asymmetry tests"),
        ],
        "diagnostics": ["ADF/KPSS", "positive/negative partial sums", "Wald asymmetry tests", "serial correlation", "heteroskedasticity", "stability"],
    },
    "decomposition": {
        "category": "Time-series decomposition",
        "label": "Classical / STL / X-13-style decomposition",
        "variants": ["classical additive", "classical multiplicative", "STL robust", "X-13/X-12 adapter when executable is configured"],
        "assumptions": [
            _assumption("Regular time spacing and meaningful seasonal period", "Decomposition requires a defensible periodic structure.", "frequency/period check"),
            _assumption("Positive observations for multiplicative decomposition", "Multiplicative components are undefined or unstable with non-positive values.", "minimum-value check"),
        ],
        "diagnostics": ["seasonal strength", "trend strength", "remainder variance", "residual autocorrelation", "outlier review"],
    },
    "cointegration": {
        "category": "Stationary & non-stationary time series",
        "label": "Cointegration tests",
        "variants": ["Engle-Granger two-step", "Johansen trace", "Johansen max-eigenvalue"],
        "assumptions": [
            _assumption("Series integration orders are suitable", "Cointegration concerns non-stationary series sharing long-run equilibria.", "ADF/KPSS per series"),
            _assumption("Lag and deterministic specification are justified", "Johansen rank inference depends on deterministic terms and lag structure.", "AIC/BIC lag selection and sensitivity"),
        ],
        "diagnostics": ["ADF/KPSS", "Engle-Granger residual test", "Johansen trace", "Johansen max-eigen", "rank sensitivity"],
    },
    "vecm": {
        "category": "Stationary & non-stationary time series",
        "label": "Vector Error Correction Model (VECM)",
        "variants": ["trace-rank VECM", "max-eigen-rank VECM", "deterministic-term variants"],
        "assumptions": [
            _assumption("Endogenous series are cointegrated with selected rank", "VECM combines long-run equilibrium and short-run dynamics.", "Johansen rank test"),
            _assumption("Residuals are approximately white noise", "Remaining serial correlation indicates insufficient dynamics.", "Whiteness test and normality test"),
        ],
        "diagnostics": ["Johansen rank", "whiteness", "normality", "Granger causality", "adjustment coefficients", "cointegrating vectors"],
    },
    "svar": {
        "category": "Stationary & non-stationary time series",
        "label": "Structural VAR (SVAR)",
        "variants": ["A-matrix SVAR", "B-matrix SVAR", "AB SVAR", "recursive/Cholesky identification"],
        "assumptions": [
            _assumption("Underlying reduced-form VAR is stable", "Structural interpretation is not meaningful for an unstable VAR without special treatment.", "VAR roots/stability"),
            _assumption("Identification restrictions are sufficient and theory-driven", "Structural shocks cannot be recovered from reduced-form innovations without identifying restrictions.", "order/restriction count and research rationale"),
        ],
        "diagnostics": ["VAR lag selection", "stability roots", "whiteness", "normality", "impulse responses", "forecast error variance decomposition"],
    },
    "tvp_var": {
        "category": "Stationary & non-stationary time series",
        "label": "Time-Varying Parameter VAR (TVP-VAR)",
        "variants": ["state-space TVP coefficients", "MCMC-enabled adapter when PyMC is installed"],
        "assumptions": [
            _assumption("Sufficient time observations for evolving coefficients", "A high-dimensional TVP-VAR can be weakly identified in short samples.", "parameter-to-observation ratio and convergence review"),
            _assumption("State evolution is substantively defensible", "Coefficient drift is a modelling assumption, not a finding.", "state variance and sensitivity checks"),
        ],
        "diagnostics": ["filter convergence", "state-variance sensitivity", "time-varying coefficient paths", "forecast errors", "MCMC R-hat/ESS when MCMC is used"],
    },
    "volatility": {
        "category": "Volatility & financial risk",
        "label": "ARCH/GARCH family",
        "variants": ["ARCH", "GARCH", "GJR-GARCH/TARCH", "EGARCH", "DCC-GARCH"],
        "assumptions": [
            _assumption("Conditional heteroskedasticity is present or substantively expected", "Volatility models target time-varying conditional variance.", "ARCH-LM / squared-residual autocorrelation"),
            _assumption("Mean model is adequately specified", "Misspecified conditional mean can contaminate volatility dynamics.", "mean residual diagnostics"),
        ],
        "diagnostics": ["ARCH-LM", "standardized residual autocorrelation", "squared standardized residual autocorrelation", "normality/tails", "AIC/BIC", "persistence", "DCC positivity/convergence"],
        "optional_dependency": "arch",
    },
    "network": {
        "category": "Network analysis",
        "label": "Network Analysis",
        "variants": ["directed/undirected", "weighted/unweighted", "centrality", "community detection", "component analysis"],
        "assumptions": [
            _assumption("Nodes and ties have valid substantive meaning", "Network measures are only meaningful if the edge definition matches the research question.", "edge construction and missing-tie review"),
            _assumption("Direction and weights are coded consistently", "Centrality and path measures change materially with direction/weight semantics.", "network schema review"),
        ],
        "diagnostics": ["density", "components", "degree", "betweenness", "closeness", "eigenvector centrality", "PageRank", "clustering", "assortativity", "communities", "modularity"],
        "optional_dependency": "networkx",
    },
    "wavelet": {
        "category": "Machine learning & signal processing",
        "label": "Wavelet Analysis",
        "variants": ["DWT", "stationary/maximal-overlap-style wavelet transform (MODWT workflow)"],
        "assumptions": [
            _assumption("Wavelet family and decomposition level are justified", "Different bases emphasize different local frequency features.", "sensitivity across wavelets/levels"),
            _assumption("Boundary treatment is reported", "Edge effects can influence coefficients near sample boundaries.", "boundary-mode report"),
        ],
        "diagnostics": ["energy by scale", "reconstruction error", "boundary-mode disclosure", "level sensitivity"],
        "optional_dependency": "pywt",
    },
    "emd": {
        "category": "Machine learning & signal processing",
        "label": "Empirical Mode Decomposition (EMD)",
        "variants": ["EMD", "EEMD/CEEMDAN adapter when supported"],
        "assumptions": [
            _assumption("Adaptive decomposition is appropriate for the nonlinear/non-stationary signal", "IMFs are data-driven and require careful substantive interpretation.", "reconstruction error and IMF orthogonality review"),
        ],
        "diagnostics": ["number of IMFs", "reconstruction error", "energy share", "mode-mixing warning"],
        "optional_dependency": "PyEMD",
    },
    "ml_forecasting": {
        "category": "Machine learning & signal processing",
        "label": "Tree / MLP time-series forecasting",
        "variants": ["GradientBoosting", "HistGradientBoosting", "RandomForest", "MLP", "XGBoost", "LightGBM", "CatBoost"],
        "assumptions": [
            _assumption("Time order is preserved", "Random train/test splits leak future information into the past.", "rolling/expanding holdout validation"),
            _assumption("Lag features and horizon match the research objective", "Forecast performance depends on information available at forecast origin.", "feature/horizon audit"),
        ],
        "diagnostics": ["rolling holdout MAE", "RMSE", "MAPE where defined", "residual autocorrelation", "feature importance when available"],
        "optional_dependency": "sklearn",
    },
    "deep_forecasting": {
        "category": "Modern deep learning & foundational models",
        "label": "Deep neural time-series models",
        "variants": ["AE", "VAE", "CAE", "PatchTST", "Informer", "Autoformer", "N-BEATS", "N-HiTS", "DeepAR"],
        "assumptions": [
            _assumption("Sample size and compute are sufficient", "Deep models can overfit short academic datasets.", "train/validation chronology, parameter count, early stopping"),
            _assumption("Scaling, context length and horizon are pre-specified", "Architecture comparisons are not meaningful under inconsistent data windows.", "configuration audit"),
        ],
        "diagnostics": ["chronological validation loss", "MAE/RMSE", "coverage for probabilistic forecasts", "overfit gap", "training convergence"],
        "optional_dependency": "torch",
    },
    "foundation_forecasting": {
        "category": "Modern deep learning & foundational models",
        "label": "Foundation / zero-shot time-series models",
        "variants": ["TimesFM", "Chronos", "TimeGPT"],
        "assumptions": [
            _assumption("Zero-shot model is appropriate for the series frequency and horizon", "Pretraining does not guarantee validity for every domain.", "backtest against naive/statistical baselines"),
            _assumption("No future leakage in evaluation", "Zero-shot evaluation still requires a chronological holdout.", "rolling holdout"),
        ],
        "diagnostics": ["baseline-relative MAE/RMSE", "prediction interval coverage where available", "rolling-origin stability"],
    },
    "hybrid_forecasting": {
        "category": "Machine learning & signal processing",
        "label": "Prophet / NeuralProphet",
        "variants": ["Prophet", "NeuralProphet"],
        "assumptions": [
            _assumption("Trend/seasonality/holiday structure is meaningful", "Additive components should reflect the data-generating context.", "component and changepoint review"),
        ],
        "diagnostics": ["rolling cross-validation", "MAE/RMSE/MAPE", "component plots", "changepoint sensitivity"],
    },
}


def method_catalog() -> list[dict[str, Any]]:
    capability_packages = {
        "networkx": _available("networkx"),
        "sklearn": _available("sklearn"),
        "arch": _available("arch"),
        "pywt": _available("pywt"),
        "PyEMD": _available("PyEMD"),
        "torch": _available("torch"),
        "xgboost": _available("xgboost"),
        "lightgbm": _available("lightgbm"),
        "catboost": _available("catboost"),
        "prophet": _available("prophet"),
        "neuralprophet": _available("neuralprophet"),
        "chronos": _available("chronos") or _available("chronos_forecasting"),
        "timesfm": _available("timesfm"),
        "nixtla": _available("nixtla"),
        "pymc": _available("pymc"),
    }
    out = []
    for key, item in METHOD_CATALOG.items():
        record = {"id": key, **item}
        dep = item.get("optional_dependency")
        if dep:
            record["runtime_available"] = bool(capability_packages.get(str(dep), False))
            record["availability_note"] = "Ready on this deployment." if record["runtime_available"] else f"Requires optional analysis dependency: {dep}."
        else:
            record["runtime_available"] = True
            record["availability_note"] = "Core workflow available. Individual advanced variants may require optional adapters."
        if key == "foundation_forecasting":
            record["runtime_available"] = any([capability_packages["timesfm"], capability_packages["chronos"], capability_packages["nixtla"]])
            record["availability_note"] = "At least one foundation runtime is configured." if record["runtime_available"] else "Capability-gated: configure TimesFM, Chronos or TimeGPT runtime/credentials."
        elif key == "hybrid_forecasting":
            record["runtime_available"] = bool(capability_packages["prophet"] or capability_packages["neuralprophet"])
            record["availability_note"] = "At least one Prophet-family runtime is configured." if record["runtime_available"] else "Capability-gated: install Prophet and/or NeuralProphet."
        elif key == "deep_forecasting":
            # Torch enables AE/VAE/CAE. Named forecasting architectures retain their own exact runtime checks.
            record["runtime_available"] = bool(capability_packages["torch"])
            record["availability_note"] = "AE/VAE/CAE runtime ready; named forecasting architectures remain capability-checked." if record["runtime_available"] else "Capability-gated: install the exact deep-learning runtime for the selected architecture."
        out.append(record)
    return out


def _normality(series) -> dict[str, Any]:
    from scipy import stats
    s = series.dropna()
    if len(s) < 3:
        return {"test": "Shapiro-Wilk", "status": "insufficient_data"}
    # scipy warns above 5000 because the p-value may be inaccurate, so sample deterministically.
    sample = s.iloc[:5000] if len(s) > 5000 else s
    stat, p = stats.shapiro(sample)
    return {"test": "Shapiro-Wilk", "n_tested": int(len(sample)), "statistic": _f(stat), "pvalue": _f(p), "note": "For large samples, visual/residual diagnostics should carry more weight than a mechanical normality test."}


def run_t_test(df, outcome: str, variant: str, group: str = "", group_a: str = "", group_b: str = "", reference: float = 0.0, paired_with: str = "") -> dict[str, Any]:
    import numpy as np
    import pandas as pd
    from scipy import stats
    variant = str(variant or "independent_welch").lower()
    y = pd.to_numeric(df[outcome], errors="coerce")
    diagnostics: dict[str, Any] = {}
    if variant in {"one_sample", "one-sample"}:
        s = y.dropna()
        if len(s) < 3: raise ValueError("One-sample t-test requires at least three usable observations.")
        stat, p = stats.ttest_1samp(s, popmean=float(reference), nan_policy="omit")
        d = (float(s.mean()) - float(reference)) / float(s.std(ddof=1)) if float(s.std(ddof=1)) else None
        diagnostics["normality"] = _normality(s)
        return {"analysis":"t_test","variant":"one_sample","n":int(len(s)),"outcome":outcome,"reference":float(reference),"test":{"t":_f(stat),"df":int(len(s)-1),"pvalue":_f(p),"mean":_f(s.mean()),"mean_difference":_f(s.mean()-float(reference)),"ci_low":_f((s.mean()-float(reference))-stats.t.ppf(.975,len(s)-1)*s.std(ddof=1)/math.sqrt(len(s))),"ci_high":_f((s.mean()-float(reference))+stats.t.ppf(.975,len(s)-1)*s.std(ddof=1)/math.sqrt(len(s))),"cohens_d":_f(d)},"diagnostics":diagnostics}
    if variant in {"paired", "paired_t"}:
        if not paired_with: raise ValueError("Paired t-test requires a second paired measurement variable.")
        work = pd.DataFrame({"a":y,"b":pd.to_numeric(df[paired_with],errors="coerce")}).dropna()
        if len(work)<3: raise ValueError("Paired t-test requires at least three complete pairs.")
        diff=work["a"]-work["b"]; stat,p=stats.ttest_rel(work["a"],work["b"])
        d=float(diff.mean()/diff.std(ddof=1)) if float(diff.std(ddof=1)) else None
        diagnostics["difference_normality"]=_normality(diff)
        return {"analysis":"t_test","variant":"paired","n":int(len(work)),"outcome":outcome,"paired_with":paired_with,"test":{"t":_f(stat),"df":int(len(work)-1),"pvalue":_f(p),"mean_difference":_f(diff.mean()),"ci_low":_f(diff.mean()-stats.t.ppf(.975,len(diff)-1)*diff.std(ddof=1)/math.sqrt(len(diff))),"ci_high":_f(diff.mean()+stats.t.ppf(.975,len(diff)-1)*diff.std(ddof=1)/math.sqrt(len(diff))),"cohens_dz":_f(d)},"diagnostics":diagnostics}
    if not group: raise ValueError("Independent t-test requires a grouping variable.")
    work=pd.DataFrame({"y":y,"g":df[group].astype("string")}).dropna()
    levels=list(work["g"].dropna().unique())
    if group_a and group_b: levels=[str(group_a),str(group_b)]
    if len(levels)!=2: raise ValueError("Independent t-test requires exactly two selected group levels.")
    a=work.loc[work["g"]==levels[0],"y"]; b=work.loc[work["g"]==levels[1],"y"]
    if len(a)<2 or len(b)<2: raise ValueError("Each group needs at least two usable observations.")
    lev=stats.levene(a,b,center="median"); equal=variant in {"independent_student","student","pooled"}
    stat,p=stats.ttest_ind(a,b,equal_var=equal)
    # Hedges-like pooled denominator for Student; average variance denominator for Welch effect size.
    if equal:
        pooled=math.sqrt(((len(a)-1)*a.var(ddof=1)+(len(b)-1)*b.var(ddof=1))/(len(a)+len(b)-2))
    else:
        pooled=math.sqrt((a.var(ddof=1)+b.var(ddof=1))/2)
    d=(a.mean()-b.mean())/pooled if pooled else None
    if equal: dfree=len(a)+len(b)-2
    else:
        va=a.var(ddof=1)/len(a); vb=b.var(ddof=1)/len(b)
        dfree=(va+vb)**2/((va**2)/(len(a)-1)+(vb**2)/(len(b)-1)) if len(a)>1 and len(b)>1 else None
    diagnostics.update({"levene":{"statistic":_f(lev.statistic),"pvalue":_f(lev.pvalue)},"normality_group_a":_normality(a),"normality_group_b":_normality(b)})
    if equal: se=pooled*math.sqrt(1/len(a)+1/len(b)) if pooled else None
    else: se=math.sqrt(a.var(ddof=1)/len(a)+b.var(ddof=1)/len(b))
    md=float(a.mean()-b.mean()); crit=stats.t.ppf(.975,float(dfree)) if dfree else None
    return {"analysis":"t_test","variant":"independent_student" if equal else "independent_welch","n":int(len(a)+len(b)),"outcome":outcome,"group":group,"groups":[{"level":str(levels[0]),"n":int(len(a)),"mean":_f(a.mean()),"sd":_f(a.std(ddof=1))},{"level":str(levels[1]),"n":int(len(b)),"mean":_f(b.mean()),"sd":_f(b.std(ddof=1))}],"test":{"t":_f(stat),"df":_f(dfree),"pvalue":_f(p),"mean_difference":_f(md),"ci_low":_f(md-crit*se) if crit is not None and se is not None else None,"ci_high":_f(md+crit*se) if crit is not None and se is not None else None,"cohens_d":_f(d)},"diagnostics":diagnostics}


def run_anova(df, outcome: str, group: str, variant: str = "one_way", factor2: str = "") -> dict[str, Any]:
    import pandas as pd
    from scipy import stats
    from statsmodels.stats.oneway import anova_oneway
    work=df[[outcome,group]+([factor2] if factor2 else [])].copy()
    work[outcome]=pd.to_numeric(work[outcome],errors="coerce"); work=work.dropna()
    levels=list(work[group].astype("string").unique())
    if len(levels)<2: raise ValueError("ANOVA requires at least two groups.")
    arrays=[work.loc[work[group].astype("string")==lev,outcome] for lev in levels]
    lev=stats.levene(*arrays,center="median")
    variant=str(variant or "one_way").lower()
    if variant in {"welch","welch_anova"}:
        fit=anova_oneway(arrays,use_var="unequal")
        result={"statistic":_f(fit.statistic),"pvalue":_f(fit.pvalue),"df_num":_f(fit.df_num),"df_denom":_f(fit.df_denom)}
        table=[]
    else:
        import statsmodels.formula.api as smf
        from statsmodels.stats.anova import anova_lm
        from patsy.builtins import Q
        if factor2:
            formula=f'Q("{outcome}") ~ C(Q("{group}")) * C(Q("{factor2}"))'
        else:
            formula=f'Q("{outcome}") ~ C(Q("{group}"))'
        model=smf.ols(formula,data=work).fit()
        tab=anova_lm(model,typ=2)
        table=[{"term":str(idx),"sum_sq":_f(row.get("sum_sq")),"df":_f(row.get("df")),"F":_f(row.get("F")),"pvalue":_f(row.get("PR(>F)"))} for idx,row in tab.iterrows()]
        result=table[0] if table else {}
    grand=float(work[outcome].mean()); ss_total=float(((work[outcome]-grand)**2).sum()); ss_between=sum(len(a)*(float(a.mean())-grand)**2 for a in arrays)
    eta=ss_between/ss_total if ss_total else None
    df_between=max(1,len(arrays)-1); ss_within=max(0.0,ss_total-ss_between); df_within=max(1,len(work)-len(arrays)); ms_within=ss_within/df_within
    omega=(ss_between-df_between*ms_within)/(ss_total+ms_within) if (ss_total+ms_within) else None
    posthoc=[]
    try:
        from statsmodels.stats.multicomp import pairwise_tukeyhsd
        tuk=pairwise_tukeyhsd(work[outcome].astype(float),work[group].astype(str))
        rows=tuk.summary().data
        for row in rows[1:]: posthoc.append({str(k):(_f(v) if isinstance(v,(int,float)) else str(v)) for k,v in zip(rows[0],row)})
    except Exception: pass
    return {"analysis":"anova","variant":variant,"n":int(len(work)),"outcome":outcome,"group":group,"factor2":factor2 or None,"groups":[{"level":str(levl),"n":int(len(arr)),"mean":_f(arr.mean()),"sd":_f(arr.std(ddof=1))} for levl,arr in zip(levels,arrays)],"test":result,"anova_table":table,"effect_size":{"eta_squared":_f(eta),"omega_squared":_f(max(0.0,omega)) if omega is not None else None},"posthoc":posthoc,"diagnostics":{"levene":{"statistic":_f(lev.statistic),"pvalue":_f(lev.pvalue)},"normality_by_group":[{"group":str(levl),**_normality(arr)} for levl,arr in zip(levels,arrays)]}}


def _dummy_design(df, predictors: list[str], categorical: list[str] | None = None):
    import pandas as pd
    categorical=set(categorical or [])
    parts=[]
    for c in predictors:
        if c in categorical or not pd.api.types.is_numeric_dtype(df[c]):
            parts.append(pd.get_dummies(df[c].astype("string"),prefix=str(c),drop_first=True,dtype=float))
        else:
            parts.append(pd.DataFrame({str(c):pd.to_numeric(df[c],errors="coerce")}))
    return pd.concat(parts,axis=1) if parts else pd.DataFrame(index=df.index)


def run_ancova(df, outcome: str, group: str, covariates: list[str], factor2: str = "", robust: bool = False) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    from scipy import stats
    cols=[outcome,group]+covariates+([factor2] if factor2 else [])
    work=df[cols].copy(); work[outcome]=pd.to_numeric(work[outcome],errors="coerce")
    for c in covariates: work[c]=pd.to_numeric(work[c],errors="coerce")
    work=work.dropna()
    if work[group].nunique()<2: raise ValueError("ANCOVA requires at least two groups.")
    # First test homogeneity of regression slopes by adding group x covariate interactions.
    Xbase=_dummy_design(work,[group]+covariates+([factor2] if factor2 else []),[group]+([factor2] if factor2 else []))
    Xbase=sm.add_constant(Xbase,has_constant="add")
    fit=sm.OLS(work[outcome].astype(float),Xbase.astype(float)).fit(cov_type="HC3" if robust else "nonrobust")
    interaction_tests=[]
    group_dummies=[c for c in Xbase.columns if str(c).startswith(f"{group}_")]
    for cov in covariates:
        for gd in group_dummies:
            name=f"{gd}__x__{cov}"
            Xbase[name]=Xbase[gd]*work[cov].astype(float)
    if any("__x__" in str(c) for c in Xbase.columns):
        full=sm.OLS(work[outcome].astype(float),Xbase.astype(float)).fit()
        terms=[c for c in Xbase.columns if "__x__" in str(c)]
        try:
            restriction=" = 0, ".join(terms)+" = 0"
            ft=full.f_test(restriction)
            interaction_tests.append({"test":"homogeneity_of_regression_slopes","F":_f(ft.fvalue),"pvalue":_f(ft.pvalue),"terms":terms})
        except Exception: pass
    # Refit adjusted model without interactions.
    X=_dummy_design(work,[group]+covariates+([factor2] if factor2 else []),[group]+([factor2] if factor2 else [])); X=sm.add_constant(X,has_constant="add")
    fit=sm.OLS(work[outcome].astype(float),X.astype(float)).fit(cov_type="HC3" if robust else "nonrobust")
    conf=fit.conf_int(); params=[]
    for name in fit.params.index:
        params.append({"term":str(name),"coefficient":_f(fit.params[name]),"std_error":_f(fit.bse[name]),"statistic":_f(fit.tvalues[name]),"pvalue":_f(fit.pvalues[name]),"ci_low":_f(conf.loc[name].iloc[0]),"ci_high":_f(conf.loc[name].iloc[1])})
    try:
        lev=stats.levene(*[work.loc[work[group]==g,outcome] for g in work[group].unique()],center="median")
        levd={"statistic":_f(lev.statistic),"pvalue":_f(lev.pvalue)}
    except Exception: levd={}
    return {"analysis":"ancova","n":int(len(work)),"outcome":outcome,"group":group,"covariates":covariates,"factor2":factor2 or None,"parameters":params,"model":{"r_squared":_f(fit.rsquared),"adjusted_r_squared":_f(fit.rsquared_adj),"f_statistic":_f(fit.fvalue),"f_pvalue":_f(fit.f_pvalue)},"diagnostics":{"homogeneity_of_regression_slopes":interaction_tests,"levene":levd,"residual_normality":_normality(fit.resid)}}


def run_manova(df, outcomes: list[str], predictors: list[str], categorical: list[str] | None = None) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.multivariate.manova import MANOVA
    cols=list(dict.fromkeys(outcomes+predictors)); work=df[cols].dropna().copy()
    if len(outcomes)<2: raise ValueError("MANOVA requires at least two dependent variables.")
    for c in outcomes: work[c]=pd.to_numeric(work[c],errors="coerce")
    work=work.dropna()
    X=_dummy_design(work,predictors,categorical); X=sm.add_constant(X,has_constant="add").astype(float)
    Y=work[outcomes].apply(pd.to_numeric,errors="coerce").astype(float)
    valid=Y.notna().all(axis=1)&X.notna().all(axis=1); X=X.loc[valid]; Y=Y.loc[valid]
    if len(Y)<max(10,len(X.columns)+3): raise ValueError("Not enough complete cases for MANOVA.")
    fit=MANOVA(Y,X)
    mv=fit.mv_test()
    tests=[]
    for term,res in mv.results.items():
        stat=res.get("stat")
        if stat is None: continue
        for index,row in stat.iterrows():
            tests.append({"term":str(term),"test":str(index),"value":_f(row.get("Value")),"F":_f(row.get("F Value")),"df_num":_f(row.get("Num DF")),"df_denom":_f(row.get("Den DF")),"pvalue":_f(row.get("Pr > F"))})
    return {"analysis":"manova","n":int(len(Y)),"outcomes":outcomes,"predictors":predictors,"multivariate_tests":tests,"diagnostics":{"outcome_normality":[{"outcome":c,**_normality(Y[c])} for c in outcomes],"covariance_note":"Review covariance-matrix homogeneity and multivariate outliers, especially for small or strongly unbalanced groups."}}


def run_quantile(df, dependent: str, predictors: list[str], quantiles: list[float] | None = None) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.regression.quantile_regression import QuantReg
    quantiles=quantiles or [0.25,0.5,0.75]
    work=df[[dependent]+predictors].copy()
    for c in [dependent]+predictors: work[c]=pd.to_numeric(work[c],errors="coerce")
    work=work.dropna(); X=sm.add_constant(work[predictors],has_constant="add")
    models=[]
    for q in sorted(set(float(x) for x in quantiles if 0<float(x)<1)):
        fit=QuantReg(work[dependent],X).fit(q=q,max_iter=5000)
        ci=fit.conf_int(); params=[]
        for name in fit.params.index:
            params.append({"term":str(name),"coefficient":_f(fit.params[name]),"std_error":_f(fit.bse[name]),"statistic":_f(fit.tvalues[name]),"pvalue":_f(fit.pvalues[name]),"ci_low":_f(ci.loc[name].iloc[0]),"ci_high":_f(ci.loc[name].iloc[1])})
        models.append({"quantile":q,"pseudo_r_squared":_f(getattr(fit,"prsquared",None)),"parameters":params})
    return {"analysis":"quantile_regression","n":int(len(work)),"dependent":dependent,"predictors":predictors,"quantile_models":models,"diagnostics":{"comparison_note":"Compare coefficient direction and magnitude across quantiles; do not interpret quantile coefficients as conditional-mean OLS effects."}}


def _ts_data(df, time_variable: str, variables: list[str]):
    import pandas as pd
    data=df[[time_variable]+variables].copy(); data[time_variable]=pd.to_datetime(data[time_variable],errors="coerce")
    for c in variables: data[c]=pd.to_numeric(data[c],errors="coerce")
    return data.dropna().sort_values(time_variable).set_index(time_variable)


def stationarity_bundle(data) -> dict[str, Any]:
    from statsmodels.tsa.stattools import adfuller, kpss
    out={}
    for col in data.columns:
        s=data[col].dropna(); item={}
        if len(s)>=12:
            try:
                a=adfuller(s,autolag="AIC"); item["adf"]={"statistic":_f(a[0]),"pvalue":_f(a[1]),"lags":int(a[2]),"nobs":int(a[3])}
            except Exception as exc: item["adf"]={"error":str(exc)}
            try:
                k=kpss(s,regression="c",nlags="auto"); item["kpss"]={"statistic":_f(k[0]),"pvalue":_f(k[1]),"lags":int(k[2])}
            except Exception as exc: item["kpss"]={"error":str(exc)}
        out[str(col)]=item
    return out


def _ols_diagnostics(fit) -> dict[str, Any]:
    from statsmodels.stats.diagnostic import acorr_breusch_godfrey, het_breuschpagan, het_white, linear_reset
    from statsmodels.stats.outliers_influence import OLSInfluence, variance_inflation_factor
    from statsmodels.stats.stattools import durbin_watson, jarque_bera
    import numpy as np
    out={}
    try:
        bg=acorr_breusch_godfrey(fit,nlags=min(4,max(1,int(math.sqrt(fit.nobs))//2))); out["breusch_godfrey"]={"lm":_f(bg[0]),"lm_pvalue":_f(bg[1]),"f":_f(bg[2]),"f_pvalue":_f(bg[3])}
    except Exception: pass
    try:
        bp=het_breuschpagan(fit.resid,fit.model.exog); out["breusch_pagan"]={"lm":_f(bp[0]),"lm_pvalue":_f(bp[1]),"f":_f(bp[2]),"f_pvalue":_f(bp[3])}
    except Exception: pass
    try:
        wh=het_white(fit.resid,fit.model.exog); out["white"]={"lm":_f(wh[0]),"lm_pvalue":_f(wh[1]),"f":_f(wh[2]),"f_pvalue":_f(wh[3])}
    except Exception: pass
    try:
        jb=jarque_bera(fit.resid); out["jarque_bera"]={"statistic":_f(jb[0]),"pvalue":_f(jb[1]),"skew":_f(jb[2]),"kurtosis":_f(jb[3])}
    except Exception: pass
    try: out["durbin_watson"]=_f(durbin_watson(fit.resid))
    except Exception: pass
    try:
        rs=linear_reset(fit,power=2,use_f=True); out["ramsey_reset"]={"F":_f(rs.fvalue),"pvalue":_f(rs.pvalue)}
    except Exception: pass
    try:
        arr=np.asarray(fit.model.exog,float); names=list(fit.model.exog_names); out["vif"]=[{"variable":str(n),"vif":_f(variance_inflation_factor(arr,i))} for i,n in enumerate(names) if str(n).lower() not in {"const","intercept"}]
    except Exception: pass
    try:
        infl=OLSInfluence(fit); cooks=infl.cooks_distance[0]; lev=infl.hat_matrix_diag
        out["influence"]={"max_cooks_distance":_f(max(cooks)),"max_leverage":_f(max(lev)),"cooks_over_4n":int((cooks>4/max(1,len(cooks))).sum())}
    except Exception: pass
    return out


def run_dols(df, dependent: str, regressors: list[str], time_variable: str, leads: int = 1, lags: int = 1, trend: bool = False) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    from statsmodels.stats.sandwich_covariance import cov_hac
    from statsmodels.tsa.stattools import coint
    data=_ts_data(df,time_variable,[dependent]+regressors)
    work=data.copy()
    for x in regressors:
        dx=work[x].diff()
        for k in range(-max(0,int(leads)),max(0,int(lags))+1):
            if k==0: continue
            label=f"D_{x}_{'lead' if k<0 else 'lag'}_{abs(k)}"
            work[label]=dx.shift(k)
    cols=list(regressors)+[c for c in work.columns if c.startswith("D_")]
    if trend: work["trend"]=range(1,len(work)+1); cols.append("trend")
    work=work[[dependent]+cols].dropna()
    if len(work)<max(25,len(cols)+8): raise ValueError("DOLS needs more usable time observations for the requested lead/lag structure.")
    X=sm.add_constant(work[cols],has_constant="add"); fit=sm.OLS(work[dependent],X).fit(cov_type="HAC",cov_kwds={"maxlags":max(1,int(lags)+int(leads))})
    ci=fit.conf_int(); params=[]
    for n in fit.params.index: params.append({"term":str(n),"coefficient":_f(fit.params[n]),"std_error":_f(fit.bse[n]),"statistic":_f(fit.tvalues[n]),"pvalue":_f(fit.pvalues[n]),"ci_low":_f(ci.loc[n].iloc[0]),"ci_high":_f(ci.loc[n].iloc[1])})
    coint_tests=[]
    for x in regressors:
        try:
            stat,p,crit=coint(data[dependent],data[x]); coint_tests.append({"pair":f"{dependent} ~ {x}","statistic":_f(stat),"pvalue":_f(p),"critical_1pct":_f(crit[0]),"critical_5pct":_f(crit[1]),"critical_10pct":_f(crit[2])})
        except Exception: pass
    return {"analysis":"dols","n":int(fit.nobs),"dependent":dependent,"regressors":regressors,"time_variable":time_variable,"leads":int(leads),"lags":int(lags),"trend":bool(trend),"parameters":params,"model":{"r_squared":_f(fit.rsquared),"adjusted_r_squared":_f(fit.rsquared_adj),"aic":_f(fit.aic),"bic":_f(fit.bic)},"stationarity":stationarity_bundle(data),"cointegration":coint_tests,"diagnostics":_ols_diagnostics(fit)}


def run_ardl(df, dependent: str, regressors: list[str], time_variable: str, ar_lags: int = 1, dl_lags: int = 1, trend: str = "c", bounds_case: int = 3) -> dict[str, Any]:
    from statsmodels.tsa.ardl import ARDL, UECM
    data=_ts_data(df,time_variable,[dependent]+regressors)
    if len(data)<30: raise ValueError("ARDL generally requires a longer usable time series; fewer than 30 observations remain.")
    model=ARDL(data[dependent],lags=max(1,int(ar_lags)),exog=data[regressors],order=max(0,int(dl_lags)),trend=str(trend or "c"))
    fit=model.fit()
    params=[{"term":str(k),"coefficient":_f(v),"std_error":_f(fit.bse.get(k)),"statistic":_f(fit.tvalues.get(k)),"pvalue":_f(fit.pvalues.get(k))} for k,v in fit.params.items()]
    diag={}
    for name,method in [("serial_correlation","test_serial_correlation"),("heteroskedasticity","test_heteroskedasticity"),("normality","test_normality")]:
        try:
            val=getattr(fit,method)()
            if hasattr(val,"to_dict"): diag[name]=val.to_dict()
            else: diag[name]=str(val)
        except Exception as exc: diag[name]={"note":str(exc)}
    bounds={}
    try:
        uecm=UECM.from_ardl(model).fit(); bt=uecm.bounds_test(case=int(bounds_case))
        bounds={"statistic":_f(bt.stat),"null":str(bt.null),"alternative":str(bt.alternative),"critical_values":bt.crit_vals.reset_index().to_dict(orient="records") if hasattr(bt.crit_vals,"reset_index") else str(bt.crit_vals)}
    except Exception as exc: bounds={"available":False,"note":str(exc)}
    return {"analysis":"ardl","n":int(fit.nobs),"dependent":dependent,"regressors":regressors,"time_variable":time_variable,"model":{"ar_lags":int(ar_lags),"distributed_lags":int(dl_lags),"trend":trend,"aic":_f(fit.aic),"bic":_f(fit.bic),"hqic":_f(fit.hqic)},"parameters":params,"stationarity":stationarity_bundle(data),"bounds_test":bounds,"diagnostics":diag}


def run_nardl(df, dependent: str, regressor: str, time_variable: str, p: int = 1, q: int = 1) -> dict[str, Any]:
    import pandas as pd
    import statsmodels.api as sm
    data=_ts_data(df,time_variable,[dependent,regressor])
    dx=data[regressor].diff(); data["x_pos"]=dx.clip(lower=0).fillna(0).cumsum(); data["x_neg"]=dx.clip(upper=0).fillna(0).cumsum()
    work=pd.DataFrame(index=data.index); work["dy"]=data[dependent].diff(); work["y_l1"]=data[dependent].shift(1); work["x_pos_l1"]=data["x_pos"].shift(1); work["x_neg_l1"]=data["x_neg"].shift(1)
    for lag in range(1,max(1,int(p))): work[f"dy_l{lag}"]=work["dy"].shift(lag)
    dpos=data["x_pos"].diff(); dneg=data["x_neg"].diff()
    for lag in range(0,max(1,int(q))): work[f"dpos_l{lag}"]=dpos.shift(lag); work[f"dneg_l{lag}"]=dneg.shift(lag)
    work=work.dropna(); X=sm.add_constant(work.drop(columns=["dy"]),has_constant="add"); fit=sm.OLS(work["dy"],X).fit(cov_type="HAC",cov_kwds={"maxlags":max(1,int(p),int(q))})
    ci=fit.conf_int(); params=[{"term":str(n),"coefficient":_f(fit.params[n]),"std_error":_f(fit.bse[n]),"statistic":_f(fit.tvalues[n]),"pvalue":_f(fit.pvalues[n]),"ci_low":_f(ci.loc[n].iloc[0]),"ci_high":_f(ci.loc[n].iloc[1])} for n in fit.params.index]
    asym={}
    try:
        long=fit.f_test("x_pos_l1 = x_neg_l1"); short_terms=[n for n in fit.params.index if n.startswith("dpos_") or n.startswith("dneg_")]
        asym["long_run"]={"F":_f(long.fvalue),"pvalue":_f(long.pvalue)}
        if short_terms:
            # Test equality of the sums using an R vector.
            names=list(fit.params.index); R=[0.0]*len(names)
            for i,n in enumerate(names):
                if n.startswith("dpos_"): R[i]=1.0
                elif n.startswith("dneg_"): R[i]=-1.0
            st=fit.f_test([R]); asym["short_run"]={"F":_f(st.fvalue),"pvalue":_f(st.pvalue)}
    except Exception as exc: asym["note"]=str(exc)
    return {"analysis":"nardl","n":int(fit.nobs),"dependent":dependent,"regressor":regressor,"time_variable":time_variable,"parameters":params,"model":{"p":int(p),"q":int(q),"r_squared":_f(fit.rsquared),"aic":_f(fit.aic),"bic":_f(fit.bic)},"asymmetry_tests":asym,"stationarity":stationarity_bundle(data[[dependent,regressor]]),"diagnostics":_ols_diagnostics(fit)}


def run_decomposition(df, dependent: str, time_variable: str, method: str = "stl", period: int = 12, robust: bool = True) -> dict[str, Any]:
    import numpy as np
    from statsmodels.tsa.seasonal import STL, seasonal_decompose
    data=_ts_data(df,time_variable,[dependent]); y=data[dependent]
    period=max(2,int(period)); method=str(method or "stl").lower()
    if len(y)<2*period: raise ValueError("Decomposition requires at least two full seasonal cycles for the selected period.")
    if method in {"additive","classical_additive"}:
        fit=seasonal_decompose(y,model="additive",period=period,extrapolate_trend="freq"); label="classical_additive"
    elif method in {"multiplicative","classical_multiplicative"}:
        if (y<=0).any(): raise ValueError("Multiplicative decomposition requires strictly positive observations.")
        fit=seasonal_decompose(y,model="multiplicative",period=period,extrapolate_trend="freq"); label="classical_multiplicative"
    elif method in {"x12","x13","x13_arima"}:
        # Statsmodels delegates X-13/X-12 style adjustment to an external executable.
        from statsmodels.tsa.x13 import x13_arima_analysis
        try:
            fit=x13_arima_analysis(y,x12path=os.getenv("X13PATH") or os.getenv("X12PATH") or None)
            trend=fit.trend; seasonal=fit.seasadj.rdiv(y) if hasattr(fit.seasadj,"rdiv") else y-fit.seasadj; resid=fit.irregular
            return {"analysis":"decomposition","method":"x13_x12_adapter","n":int(len(y)),"period":period,"components":[{"time":str(i),"observed":_f(y.loc[i]),"trend":_f(trend.loc[i]),"seasonal":_f(seasonal.loc[i]) if i in seasonal.index else None,"remainder":_f(resid.loc[i]) if i in resid.index else None} for i in y.index],"diagnostics":{"external_executable":"configured","note":"X-13/X-12-family seasonal adjustment was run through the statsmodels executable adapter."}}
        except Exception as exc:
            raise RuntimeError("X-13/X-12 seasonal adjustment requires a compatible external X-13/X-12 executable configured with X13PATH/X12PATH. STL remains available without it. Details: "+str(exc)) from exc
    else:
        fit=STL(y,period=period,robust=bool(robust)).fit(); label="stl"
    trend=fit.trend; seasonal=fit.seasonal; resid=fit.resid
    def strength(component):
        vr=float(np.nanvar(resid)); vc=float(np.nanvar(component+resid)); return max(0.0,1-vr/vc) if vc else None
    return {"analysis":"decomposition","method":label,"n":int(len(y)),"period":period,"components":[{"time":str(i),"observed":_f(y.loc[i]),"trend":_f(trend.loc[i]),"seasonal":_f(seasonal.loc[i]),"remainder":_f(resid.loc[i])} for i in y.index],"diagnostics":{"seasonal_strength":_f(strength(seasonal)),"trend_strength":_f(strength(trend)),"remainder_sd":_f(resid.std(ddof=1))}}


def run_cointegration(df, variables: list[str], time_variable: str, method: str = "johansen", det_order: int = 0, k_ar_diff: int = 1) -> dict[str, Any]:
    from statsmodels.tsa.stattools import coint
    from statsmodels.tsa.vector_ar.vecm import coint_johansen
    data=_ts_data(df,time_variable,variables); method=str(method or "johansen").lower()
    if len(variables)<2: raise ValueError("Cointegration testing requires at least two series.")
    if method in {"engle_granger","engle-granger","eg"}:
        rows=[]
        y=variables[0]
        for x in variables[1:]:
            stat,p,crit=coint(data[y],data[x]); rows.append({"relationship":f"{y} ~ {x}","statistic":_f(stat),"pvalue":_f(p),"critical_1pct":_f(crit[0]),"critical_5pct":_f(crit[1]),"critical_10pct":_f(crit[2])})
        return {"analysis":"cointegration","method":"engle_granger","n":int(len(data)),"variables":variables,"tests":rows,"stationarity":stationarity_bundle(data)}
    joh=coint_johansen(data[variables],det_order=int(det_order),k_ar_diff=max(0,int(k_ar_diff)))
    rows=[]
    for r in range(len(variables)):
        rows.append({"rank_h0":int(r),"trace_stat":_f(joh.trace_stat[r]),"trace_90":_f(joh.trace_stat_crit_vals[r][0]),"trace_95":_f(joh.trace_stat_crit_vals[r][1]),"trace_99":_f(joh.trace_stat_crit_vals[r][2]),"maxeig_stat":_f(joh.max_eig_stat[r]),"maxeig_90":_f(joh.max_eig_stat_crit_vals[r][0]),"maxeig_95":_f(joh.max_eig_stat_crit_vals[r][1]),"maxeig_99":_f(joh.max_eig_stat_crit_vals[r][2])})
    return {"analysis":"cointegration","method":"johansen","n":int(len(data)),"variables":variables,"tests":rows,"eigenvectors":[[ _f(x) for x in row] for row in joh.evec.tolist()],"stationarity":stationarity_bundle(data)}


def run_vecm(df, variables: list[str], time_variable: str, coint_rank: int = 1, k_ar_diff: int = 1, deterministic: str = "ci") -> dict[str, Any]:
    from statsmodels.tsa.vector_ar.vecm import VECM, select_coint_rank
    data=_ts_data(df,time_variable,variables)
    if len(variables)<2: raise ValueError("VECM requires at least two endogenous series.")
    if len(data)<30: raise ValueError("VECM generally requires a longer multivariate time series; fewer than 30 complete observations remain.")
    rank=max(1,min(int(coint_rank),len(variables)-1)); fit=VECM(data[variables],k_ar_diff=max(1,int(k_ar_diff)),coint_rank=rank,deterministic=str(deterministic or "ci")).fit()
    rank_test={}
    try:
        rt=select_coint_rank(data[variables],det_order=0,k_ar_diff=max(1,int(k_ar_diff)),method="trace",signif=.05); rank_test={"selected_rank":int(rt.rank),"summary":str(rt.summary())}
    except Exception as exc: rank_test={"note":str(exc)}
    diag={}
    try:
        wt=fit.test_whiteness(nlags=max(5,int(k_ar_diff)+2)); diag["whiteness"]={"statistic":_f(wt.test_statistic),"pvalue":_f(wt.pvalue),"df":_f(wt.df)}
    except Exception: pass
    try:
        nt=fit.test_normality(); diag["normality"]={"statistic":_f(nt.test_statistic),"pvalue":_f(nt.pvalue),"df":_f(nt.df)}
    except Exception: pass
    return {"analysis":"vecm","n":int(fit.nobs),"variables":variables,"time_variable":time_variable,"coint_rank":rank,"k_ar_diff":int(k_ar_diff),"alpha":[[_f(x) for x in row] for row in fit.alpha.tolist()],"beta":[[_f(x) for x in row] for row in fit.beta.tolist()],"gamma":[[_f(x) for x in row] for row in fit.gamma.tolist()],"rank_test":rank_test,"diagnostics":diag,"stationarity":stationarity_bundle(data)}


def _matrix_from_spec(value: Any, n: int, default: str):
    import numpy as np
    if isinstance(value,list) and len(value)==n:
        return np.array(value,dtype=object)
    mat=np.eye(n,dtype=object)
    if default=="A":
        for i in range(1,n):
            for j in range(i): mat[i,j]="E"
    elif default=="B":
        for i in range(n): mat[i,i]="E"
    return mat


def run_svar(df, variables: list[str], time_variable: str, lags: int = 1, svar_type: str = "recursive", A: Any = None, B: Any = None) -> dict[str, Any]:
    from statsmodels.tsa.api import VAR
    from statsmodels.tsa.vector_ar.svar_model import SVAR
    data=_ts_data(df,time_variable,variables)
    if len(variables)<2: raise ValueError("SVAR requires at least two endogenous series.")
    reduced=VAR(data[variables]).fit(maxlags=max(1,int(lags)),ic=None)
    stability="stable" if reduced.is_stable() else "unstable"
    diag={"stability":stability,"stable":bool(reduced.is_stable()),"roots_modulus":[_f(abs(x)) for x in reduced.roots]}
    try:
        wt=reduced.test_whiteness(nlags=max(5,int(lags)+2)); diag["whiteness"]={"statistic":_f(wt.test_statistic),"pvalue":_f(wt.pvalue)}
    except Exception: pass
    try:
        nt=reduced.test_normality(); diag["normality"]={"statistic":_f(nt.test_statistic),"pvalue":_f(nt.pvalue)}
    except Exception: pass
    params=[]
    for eq,var in enumerate(variables):
        for term in reduced.params.index:
            params.append({"equation":var,"term":str(term),"coefficient":_f(reduced.params.loc[term,var]),"pvalue":_f(reduced.pvalues.loc[term,var])})
    stype=str(svar_type or "recursive").upper()
    # Recursive Cholesky is a legitimate structural identification and avoids
    # inventing A/B restrictions when the researcher has not supplied them.
    if stype in {"RECURSIVE","CHOLESKY","CHOL"} or (A is None and B is None and stype=="A"):
        irf=reduced.irf(min(10,max(2,len(data)//8)))
        orth=irf.orth_irfs
        irf_rows=[]
        for h in range(orth.shape[0]):
            for response_i,response in enumerate(variables):
                for shock_i,shock in enumerate(variables):
                    irf_rows.append({"horizon":h,"response":response,"shock":shock,"orthogonalized_irf":_f(orth[h,response_i,shock_i])})
        diag["identification"]="recursive Cholesky ordering: "+" → ".join(variables)
        return {"analysis":"svar","model_type":"recursive_cholesky","n":int(reduced.nobs),"variables":variables,"time_variable":time_variable,"lags":int(reduced.k_ar),"parameters":params,"model":{"aic":_f(reduced.aic),"bic":_f(reduced.bic),"hqic":_f(reduced.hqic)},"impulse_responses":irf_rows,"diagnostics":diag,"stationarity":stationarity_bundle(data)}
    n=len(variables); Amat=_matrix_from_spec(A,n,"A") if stype in {"A","AB"} else None; Bmat=_matrix_from_spec(B,n,"B") if stype in {"B","AB"} else None
    if stype in {"A","AB"} and A is None: raise ValueError("Non-recursive A/AB SVAR requires an explicit theory-based A matrix. Unknown parameters must be marked 'E'.")
    if stype in {"B","AB"} and B is None: raise ValueError("B/AB SVAR requires an explicit theory-based B matrix. Unknown parameters must be marked 'E'.")
    model=SVAR(data[variables].values,svar_type=stype,A=Amat,B=Bmat); fit=model.fit(maxlags=max(1,int(lags)))
    diag["identification"]="researcher-supplied structural restrictions"
    def matrix_rows(mat):
        if mat is None: return None
        return [[str(x) if isinstance(x,str) else _f(x) for x in row] for row in mat]
    return {"analysis":"svar","model_type":stype,"n":int(reduced.nobs),"variables":variables,"time_variable":time_variable,"lags":int(reduced.k_ar),"A_matrix":matrix_rows(getattr(fit,"A",None)),"B_matrix":matrix_rows(getattr(fit,"B",None)),"parameters":params,"model":{"aic":_f(reduced.aic),"bic":_f(reduced.bic),"hqic":_f(reduced.hqic)},"diagnostics":diag,"stationarity":stationarity_bundle(data)}

def run_tvp_var(df, variables: list[str], time_variable: str, lags: int = 1, forgetting_factor: float = 0.98) -> dict[str, Any]:
    """Deterministic recursive TVP-VAR coefficient tracker.

    This state-adaptive implementation estimates equation-specific recursive
    least-squares coefficient paths. If PyMC is installed, the UI also reports
    that a full MCMC TVP-VAR adapter can be enabled, but the deterministic path
    is always available and never mislabels itself as MCMC.
    """
    import numpy as np
    data=_ts_data(df,time_variable,variables); p=max(1,int(lags)); lam=min(.9999,max(.90,float(forgetting_factor)))
    Y=data[variables].values.astype(float); k=len(variables); rows=[]
    X=[]; targets=[]; times=[]
    for t in range(p,len(Y)):
        x=[1.0]
        for lag in range(1,p+1): x.extend(Y[t-lag].tolist())
        X.append(np.asarray(x,float)); targets.append(Y[t]); times.append(data.index[t])
    if len(X)<max(20,2*(1+k*p)): raise ValueError("TVP-VAR requires more usable time observations relative to the selected lag order and number of series.")
    m=1+k*p; betas=[]
    for eq in range(k):
        beta=np.zeros(m); P=np.eye(m)*1000.0; path=[]
        for x,y,t in zip(X,targets,times):
            Px=P@x; gain=Px/(lam+x@Px); err=float(y[eq]-x@beta); beta=beta+gain*err; P=(P-np.outer(gain,x)@P)/lam
            path.append({"time":str(t),"coefficients":[_f(v) for v in beta],"forecast_error":_f(err)})
        betas.append({"equation":variables[eq],"path":path[-200:],"final_coefficients":[_f(v) for v in beta]})
    labels=["const"]+[f"L{lag}.{v}" for lag in range(1,p+1) for v in variables]
    return {"analysis":"tvp_var","n":int(len(X)),"variables":variables,"time_variable":time_variable,"lags":p,"forgetting_factor":lam,"coefficient_labels":labels,"equations":betas,"diagnostics":{"estimator":"recursive least squares state-adaptive TVP coefficients","mcmc_adapter_available":_available("pymc"),"note":"This run is deterministic RLS, not MCMC. Use the optional PyMC adapter only when Bayesian TVP-VAR/MCMC is explicitly required."},"stationarity":stationarity_bundle(data)}


def run_volatility(df, dependent: str, time_variable: str, model: str = "garch", p: int = 1, q: int = 1, o: int = 0, distribution: str = "normal") -> dict[str, Any]:
    if not _available("arch"):
        raise RuntimeError("ARCH/GARCH execution requires the optional 'arch' package. Add requirements-advanced-analysis.txt to the deployment build. ProjectReady will not approximate GARCH with ordinary regression.")
    from arch import arch_model
    data=_ts_data(df,time_variable,[dependent]); y=data[dependent]
    model=str(model or "garch").lower(); vol="ARCH" if model=="arch" else "GARCH" if model in {"garch","gjr_garch","tarch"} else "EGARCH" if model=="egarch" else "GARCH"
    pp=max(1,int(p)); qq=0 if model=="arch" else max(1,int(q)); oo=max(1,int(o)) if model in {"gjr_garch","tarch"} else 0
    am=arch_model(y,mean="Constant",vol=vol,p=pp,o=oo,q=qq,dist=str(distribution or "normal")); fit=am.fit(disp="off")
    params=[{"term":str(k),"coefficient":_f(v),"std_error":_f(fit.std_err.get(k)),"statistic":_f(fit.tvalues.get(k)),"pvalue":_f(fit.pvalues.get(k))} for k,v in fit.params.items()]
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
    sr=fit.std_resid.dropna(); diag={}
    try:
        lb=acorr_ljungbox(sr,lags=[min(10,max(2,len(sr)//10))],return_df=True).iloc[-1]; diag["ljung_box_standardized"]={"statistic":_f(lb["lb_stat"]),"pvalue":_f(lb["lb_pvalue"])}
        lbs=acorr_ljungbox(sr**2,lags=[min(10,max(2,len(sr)//10))],return_df=True).iloc[-1]; diag["ljung_box_squared"]={"statistic":_f(lbs["lb_stat"]),"pvalue":_f(lbs["lb_pvalue"])}
        ar=het_arch(sr,nlags=min(10,max(2,len(sr)//10))); diag["arch_lm_after_fit"]={"lm":_f(ar[0]),"lm_pvalue":_f(ar[1])}
    except Exception: pass
    persistence=sum(float(v) for k,v in fit.params.items() if "alpha" in str(k).lower() or "beta" in str(k).lower())
    return {"analysis":"volatility","model_type":model,"n":int(fit.nobs),"dependent":dependent,"time_variable":time_variable,"parameters":params,"model":{"log_likelihood":_f(fit.loglikelihood),"aic":_f(fit.aic),"bic":_f(fit.bic),"persistence":_f(persistence)},"diagnostics":diag,"conditional_volatility_preview":[{"time":str(i),"volatility":_f(v)} for i,v in fit.conditional_volatility.tail(60).items()]}


def run_dcc_garch(df, variables: list[str], time_variable: str, p: int = 1, q: int = 1) -> dict[str, Any]:
    if not _available("arch"):
        raise RuntimeError("DCC-GARCH requires the optional 'arch' package for the univariate GARCH margins. Add requirements-advanced-analysis.txt to the deployment build.")
    import numpy as np
    from arch import arch_model
    from scipy.optimize import minimize
    data=_ts_data(df,time_variable,variables)
    if len(variables)<2: raise ValueError("DCC-GARCH requires at least two return/innovation series.")
    z=[]; margins=[]
    for col in variables:
        fit=arch_model(data[col],mean="Constant",vol="GARCH",p=max(1,int(p)),q=max(1,int(q)),dist="normal").fit(disp="off")
        std=fit.std_resid.reindex(data.index); z.append(std.values); margins.append({"variable":col,"aic":_f(fit.aic),"bic":_f(fit.bic),"parameters":{str(k):_f(v) for k,v in fit.params.items()}})
    Z=np.column_stack(z); mask=np.isfinite(Z).all(axis=1); Z=Z[mask]; idx=data.index[mask]
    S=np.corrcoef(Z,rowvar=False); k=len(variables)
    def objective(theta):
        a,b=theta
        if a<0 or b<0 or a+b>=.999: return 1e12
        Q=S.copy(); total=0.0
        for t in range(1,len(Z)):
            Q=(1-a-b)*S+a*np.outer(Z[t-1],Z[t-1])+b*Q
            d=np.sqrt(np.clip(np.diag(Q),1e-10,None)); R=Q/np.outer(d,d)
            try:
                sign,logdet=np.linalg.slogdet(R); inv=np.linalg.inv(R)
                if sign<=0: return 1e12
                total += logdet + Z[t]@inv@Z[t]
            except Exception: return 1e12
        return .5*total
    opt=minimize(objective,[.03,.94],bounds=[(1e-6,.5),(1e-6,.999)],method="L-BFGS-B")
    a,b=map(float,opt.x); Q=S.copy(); previews=[]
    for t in range(1,len(Z)):
        Q=(1-a-b)*S+a*np.outer(Z[t-1],Z[t-1])+b*Q; d=np.sqrt(np.clip(np.diag(Q),1e-10,None)); R=Q/np.outer(d,d)
        if t>=len(Z)-60:
            previews.append({"time":str(idx[t]),"correlations":[{"pair":f"{variables[i]} ↔ {variables[j]}","correlation":_f(R[i,j])} for i in range(k) for j in range(i+1,k)]})
    return {"analysis":"dcc_garch","n":int(len(Z)),"variables":variables,"time_variable":time_variable,"margins":margins,"dcc_parameters":{"alpha":_f(a),"beta":_f(b),"persistence":_f(a+b)},"optimizer":{"success":bool(opt.success),"message":str(opt.message),"objective":_f(opt.fun)},"dynamic_correlations_preview":previews,"diagnostics":{"positive_parameter_constraints":bool(a>=0 and b>=0 and a+b<1),"note":"DCC is estimated after univariate GARCH standardisation; review the adequacy of every marginal GARCH model before interpreting correlations."}}


def network_svg(G, communities: list[set] | None = None) -> str:
    import networkx as nx
    pos=nx.spring_layout(G,seed=20260816,weight="weight",iterations=120)
    width,height=1200,780; margin=70
    xs=[v[0] for v in pos.values()]; ys=[v[1] for v in pos.values()]; xmin,xmax=min(xs),max(xs); ymin,ymax=min(ys),max(ys)
    def mapx(x): return margin+(x-xmin)/(max(1e-9,xmax-xmin))*(width-2*margin)
    def mapy(y): return margin+(y-ymin)/(max(1e-9,ymax-ymin))*(height-2*margin)
    comm_index={}
    for i,c in enumerate(communities or []):
        for n in c: comm_index[n]=i
    parts=[f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 {width} {height}' width='{width}' height='{height}'>","<rect width='100%' height='100%' rx='18' fill='white'/>","<text x='28' y='34' font-family='Arial,sans-serif' font-size='14' fill='#667085'>ProjectReady network analysis · deterministic layout seed</text>"]
    for u,v,d in G.edges(data=True):
        x1,y1=mapx(pos[u][0]),mapy(pos[u][1]); x2,y2=mapx(pos[v][0]),mapy(pos[v][1]); w=float(d.get("weight",1) or 1); sw=max(.7,min(5,1+math.log1p(abs(w))))
        parts.append(f"<line x1='{x1:.1f}' y1='{y1:.1f}' x2='{x2:.1f}' y2='{y2:.1f}' stroke='#9aa4b2' stroke-opacity='.58' stroke-width='{sw:.1f}'/>")
    degree=dict(G.degree(weight="weight"))
    maxd=max([abs(float(v)) for v in degree.values()] or [1])
    for n in G.nodes:
        x,y=mapx(pos[n][0]),mapy(pos[n][1]); r=10+16*abs(float(degree.get(n,0)))/maxd; ci=comm_index.get(n,-1)
        # Accessible neutral palette generated without requiring static colour assignment per chart.
        fills=["#e8eef8","#eef5e9","#f7eee5","#f4e9f4","#e8f4f4","#f6f2df"]
        fill=fills[ci%len(fills)] if ci>=0 else "#eef2f6"
        parts.append(f"<circle cx='{x:.1f}' cy='{y:.1f}' r='{r:.1f}' fill='{fill}' stroke='#25324a' stroke-width='1.8'/>")
        label=str(n); parts.append(f"<text x='{x:.1f}' y='{y+r+16:.1f}' text-anchor='middle' font-family='Arial,sans-serif' font-size='12' fill='#182235'>{_xml(label[:28])}</text>")
    parts.append("</svg>"); return "".join(parts)


def _xml(value: Any) -> str:
    return str(value or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("'","&apos;").replace('"',"&quot;")


def run_network(df, source: str, target: str, weight: str = "", directed: bool = False) -> dict[str, Any]:
    if not _available("networkx"):
        raise RuntimeError("Network analysis requires networkx. Add requirements-advanced-analysis.txt to the deployment build.")
    import networkx as nx
    cols=[source,target]+([weight] if weight else []); work=df[cols].dropna().copy(); G=nx.DiGraph() if directed else nx.Graph()
    for _,row in work.iterrows():
        u=str(row[source]); v=str(row[target]); w=1.0
        if weight:
            try: w=float(row[weight])
            except Exception: continue
        if G.has_edge(u,v): G[u][v]["weight"]=float(G[u][v].get("weight",0))+w
        else: G.add_edge(u,v,weight=w)
    if G.number_of_nodes()<2: raise ValueError("Network analysis requires at least two connected nodes.")
    cent={"degree":nx.degree_centrality(G),"betweenness":nx.betweenness_centrality(G,weight="weight",normalized=True),"closeness":nx.closeness_centrality(G),"pagerank":nx.pagerank(G,weight="weight")}
    try: cent["eigenvector"]=nx.eigenvector_centrality(G,max_iter=2000,weight="weight")
    except Exception: cent["eigenvector"]={}
    comm=[]; modularity=None
    try:
        base=G.to_undirected(); comm=list(nx.community.louvain_communities(base,weight="weight",seed=20260816)); modularity=nx.community.modularity(base,comm,weight="weight")
    except Exception: pass
    rows=[]
    for n in G.nodes:
        rows.append({"node":str(n),"degree":_f(cent["degree"].get(n)),"betweenness":_f(cent["betweenness"].get(n)),"closeness":_f(cent["closeness"].get(n)),"eigenvector":_f(cent["eigenvector"].get(n)),"pagerank":_f(cent["pagerank"].get(n)),"community":next((i+1 for i,c in enumerate(comm) if n in c),None)})
    rows.sort(key=lambda x:(x.get("pagerank") or 0),reverse=True)
    und=G.to_undirected(); diagnostics={"nodes":G.number_of_nodes(),"edges":G.number_of_edges(),"density":_f(nx.density(G)),"components":nx.number_connected_components(und),"average_clustering":_f(nx.average_clustering(und,weight="weight")),"degree_assortativity":_f(nx.degree_assortativity_coefficient(G,weight="weight")),"communities":len(comm),"modularity":_f(modularity)}
    if directed: diagnostics["reciprocity"]=_f(nx.reciprocity(G))
    return {"analysis":"network","n":int(len(work)),"source":source,"target":target,"weight":weight or None,"directed":bool(directed),"network":diagnostics,"centrality":rows,"communities":[{"community":i+1,"nodes":[str(x) for x in sorted(c,key=str)]} for i,c in enumerate(comm)],"diagram_svg":network_svg(G,comm)}


def run_wavelet(df, dependent: str, time_variable: str, method: str = "dwt", wavelet: str = "db4", level: int = 3) -> dict[str, Any]:
    if not _available("pywt"):
        raise RuntimeError("DWT/MODWT execution requires PyWavelets. Add requirements-advanced-analysis.txt to the deployment build.")
    import numpy as np
    import pywt
    data=_ts_data(df,time_variable,[dependent]); y=data[dependent].values.astype(float); level=max(1,int(level)); method=str(method or "dwt").lower()
    if method in {"modwt","swt","maximal_overlap"}:
        max_level=pywt.swt_max_level(len(y)); use=min(level,max_level)
        if use<1: raise ValueError("Series length is too short for the requested maximal-overlap/stationary wavelet level.")
        coeffs=pywt.swt(y,wavelet,level=use,trim_approx=False,norm=True); scales=[]
        for i,(ca,cd) in enumerate(coeffs,1): scales.append({"level":i,"approximation_energy":_f(np.sum(ca**2)),"detail_energy":_f(np.sum(cd**2))})
        rec=pywt.iswt(coeffs,wavelet,norm=True); label="modwt_stationary_wavelet"
    else:
        coeffs=pywt.wavedec(y,wavelet,level=level,mode="symmetric"); rec=pywt.waverec(coeffs,wavelet,mode="symmetric")[:len(y)]; scales=[{"component":"approximation_L"+str(level),"energy":_f(np.sum(coeffs[0]**2))}]+[{"component":f"detail_L{level-i+1}","energy":_f(np.sum(c**2))} for i,c in enumerate(coeffs[1:],1)]; label="dwt"
    err=float(np.sqrt(np.mean((y-np.asarray(rec)[:len(y)])**2)))
    return {"analysis":"wavelet","method":label,"n":int(len(y)),"dependent":dependent,"time_variable":time_variable,"wavelet":wavelet,"level":level,"scale_energy":scales,"diagnostics":{"reconstruction_rmse":_f(err),"boundary_mode":"symmetric" if label=="dwt" else "periodic stationary transform","note":"The MODWT workflow uses the non-decimated stationary wavelet transform implementation and reports this explicitly rather than presenting it as a different algorithm silently."}}


def run_emd(df, dependent: str, time_variable: str, method: str = "emd") -> dict[str, Any]:
    if not _available("PyEMD"):
        raise RuntimeError("EMD/EEMD/CEEMDAN execution requires the optional EMD-signal (PyEMD) package. Add requirements-advanced-analysis.txt to the deployment build.")
    import numpy as np
    from PyEMD import EMD, EEMD, CEEMDAN
    data=_ts_data(df,time_variable,[dependent]); y=data[dependent].values.astype(float); method=str(method or "emd").lower()
    cls=EEMD if method=="eemd" else CEEMDAN if method=="ceemdan" else EMD; imfs=cls()(y)
    recon=imfs.sum(axis=0); total=float(np.sum(y**2)) or 1.0
    rows=[{"imf":i+1,"energy":_f(np.sum(imf**2)),"energy_share":_f(np.sum(imf**2)/total)} for i,imf in enumerate(imfs)]
    return {"analysis":"emd","method":method,"n":int(len(y)),"dependent":dependent,"time_variable":time_variable,"imfs":rows,"diagnostics":{"number_of_imfs":int(len(imfs)),"reconstruction_rmse":_f(np.sqrt(np.mean((y-recon)**2))),"mode_mixing_note":"Inspect IMF frequencies and substantive meaning; EMD components are adaptive and should not be interpreted mechanically."}}


def _lagged_supervised(series, lags: int, horizon: int = 1):
    import numpy as np
    y=np.asarray(series,float); X=[]; t=[]
    for i in range(lags,len(y)-horizon+1): X.append(y[i-lags:i]); t.append(y[i+horizon-1])
    return np.asarray(X,float),np.asarray(t,float)


def run_ml_forecast(df, dependent: str, time_variable: str, model: str = "gradient_boosting", lags: int = 12, horizon: int = 1, test_fraction: float = .2) -> dict[str, Any]:
    if not _available("sklearn"): raise RuntimeError("Machine-learning forecasting requires scikit-learn.")
    import numpy as np
    from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor, RandomForestRegressor
    from sklearn.neural_network import MLPRegressor
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    data=_ts_data(df,time_variable,[dependent]); X,y=_lagged_supervised(data[dependent].values,max(2,int(lags)),max(1,int(horizon)))
    if len(y)<30: raise ValueError("Machine-learning forecasting requires more lagged training cases; fewer than 30 supervised rows remain.")
    split=max(10,int(len(y)*(1-min(.5,max(.1,float(test_fraction)))))); Xtr,Xte=X[:split],X[split:]; ytr,yte=y[:split],y[split:]
    key=str(model or "gradient_boosting").lower(); optional=None
    if key=="hist_gradient_boosting": est=HistGradientBoostingRegressor(random_state=20260816)
    elif key=="random_forest": est=RandomForestRegressor(n_estimators=300,random_state=20260816,n_jobs=-1)
    elif key=="mlp": est=MLPRegressor(hidden_layer_sizes=(64,32),random_state=20260816,max_iter=1500,early_stopping=True)
    elif key=="xgboost":
        if not _available("xgboost"): raise RuntimeError("XGBoost adapter requires the xgboost package from requirements-advanced-ml.txt.")
        from xgboost import XGBRegressor; est=XGBRegressor(n_estimators=500,max_depth=4,learning_rate=.05,subsample=.9,colsample_bytree=.9,random_state=20260816)
    elif key=="lightgbm":
        if not _available("lightgbm"): raise RuntimeError("LightGBM adapter requires the lightgbm package from requirements-advanced-ml.txt.")
        from lightgbm import LGBMRegressor; est=LGBMRegressor(n_estimators=500,learning_rate=.05,random_state=20260816)
    elif key=="catboost":
        if not _available("catboost"): raise RuntimeError("CatBoost adapter requires the catboost package from requirements-advanced-ml.txt.")
        from catboost import CatBoostRegressor; est=CatBoostRegressor(iterations=500,learning_rate=.05,depth=6,verbose=False,random_seed=20260816)
    else: est=GradientBoostingRegressor(random_state=20260816,n_estimators=300,learning_rate=.05,max_depth=3)
    est.fit(Xtr,ytr); pred=est.predict(Xte); mae=float(mean_absolute_error(yte,pred)); rmse=float(mean_squared_error(yte,pred)**.5); denom=np.where(np.abs(yte)>1e-12,np.abs(yte),np.nan); mape=float(np.nanmean(np.abs((yte-pred)/denom))*100) if np.isfinite(denom).any() else None
    imp=[]
    if hasattr(est,"feature_importances_"): imp=[{"lag":int(max(2,int(lags))-i),"importance":_f(v)} for i,v in enumerate(est.feature_importances_)]
    return {"analysis":"ml_forecasting","model_type":key,"n":int(len(y)),"train_n":int(len(ytr)),"test_n":int(len(yte)),"dependent":dependent,"time_variable":time_variable,"lags":int(lags),"horizon":int(horizon),"metrics":{"mae":_f(mae),"rmse":_f(rmse),"mape_percent":_f(mape)},"feature_importance":imp,"forecast_holdout":[{"actual":_f(a),"predicted":_f(p)} for a,p in zip(yte[-100:],pred[-100:])],"diagnostics":{"chronological_split":True,"random_shuffle":False,"note":"The holdout is the most recent portion of the series. For publication, add rolling-origin validation and compare against naive/statistical baselines."}}


def deep_capability(model: str) -> dict[str, Any]:
    key=str(model or "").lower()
    mapping={
        "ae":("torch","Vanilla autoencoder anomaly-detection adapter"),"vae":("torch","Variational autoencoder adapter"),"cae":("torch","1D convolutional autoencoder adapter"),
        "patchtst":("transformers","PatchTST adapter"),"informer":("transformers","Informer adapter"),"autoformer":("transformers","Autoformer adapter"),
        "nbeats":("neuralforecast","N-BEATS adapter"),"nhits":("neuralforecast","N-HiTS adapter"),"deepar":("gluonts","DeepAR adapter"),
        "chronos":("chronos","Chronos zero-shot adapter"),"timesfm":("timesfm","TimesFM zero-shot adapter"),"timegpt":("nixtla","TimeGPT API adapter"),
        "prophet":("prophet","Prophet adapter"),"neuralprophet":("neuralprophet","NeuralProphet adapter"),
    }
    dep,label=mapping.get(key,("","Advanced model adapter")); available=bool(dep and (_available(dep) or (dep=="chronos" and _available("chronos_forecasting"))))
    if key=="timegpt": available=available and bool(os.getenv("TIMEGPT_API_KEY") or os.getenv("NIXTLA_API_KEY"))
    return {"analysis":"advanced_forecasting_adapter","model_type":key,"runtime_available":available,"required_dependency":dep,"label":label,"message":"Runtime adapter is available on this deployment." if available else f"{label} is included as a capability-checked adapter but is not active until the optional '{dep}' dependency"+(" and API key" if key=="timegpt" else "")+" are configured. ProjectReady will not substitute a different model and call it "+key+"."}


def run_torch_autoencoder(
    df,
    dependent: str,
    time_variable: str,
    model_type: str = "ae",
    window: int = 24,
    epochs: int = 120,
    latent_dim: int = 8,
    test_fraction: float = 0.2,
) -> dict[str, Any]:
    """Fit an AE/VAE/1-D CAE to chronological time-series windows.

    The output is for representation/anomaly diagnostics.  It never promotes
    reconstructed or VAE-generated observations to observed research data.
    """
    if not _available("torch"):
        raise RuntimeError("AE/VAE/CAE analysis requires the optional torch runtime.")
    import numpy as np
    import torch
    from torch import nn

    data = _ts_data(df, time_variable, [dependent])
    values = np.asarray(data[dependent], dtype=np.float32)
    w = max(4, int(window))
    if len(values) < max(60, 3 * w):
        raise ValueError("Deep autoencoder analysis needs at least 60 observations and enough cases for the selected context window.")
    mean = float(np.nanmean(values)); sd = float(np.nanstd(values)) or 1.0
    z = (values - mean) / sd
    X = np.stack([z[i-w:i] for i in range(w, len(z)+1)], axis=0).astype(np.float32)
    split = min(len(X)-10, max(20, int(len(X) * (1 - min(.45, max(.1, float(test_fraction)))))))
    Xtr = torch.tensor(X[:split]); Xte = torch.tensor(X[split:])
    torch.manual_seed(20260816)
    key = str(model_type or "ae").lower()
    ld = max(2, min(int(latent_dim), max(2, w // 2)))

    class AE(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc = nn.Sequential(nn.Linear(w, max(16, w)), nn.ReLU(), nn.Linear(max(16, w), ld))
            self.dec = nn.Sequential(nn.Linear(ld, max(16, w)), nn.ReLU(), nn.Linear(max(16, w), w))
        def forward(self, x): return self.dec(self.enc(x))

    class VAE(nn.Module):
        def __init__(self):
            super().__init__(); h=max(16,w)
            self.h=nn.Sequential(nn.Linear(w,h),nn.ReLU()); self.mu=nn.Linear(h,ld); self.lv=nn.Linear(h,ld)
            self.dec=nn.Sequential(nn.Linear(ld,h),nn.ReLU(),nn.Linear(h,w))
        def forward(self,x):
            h=self.h(x); mu=self.mu(h); lv=self.lv(h); eps=torch.randn_like(mu); zz=mu+torch.exp(.5*lv)*eps
            return self.dec(zz),mu,lv

    class CAE(nn.Module):
        def __init__(self):
            super().__init__()
            self.enc=nn.Sequential(nn.Conv1d(1,8,3,padding=1),nn.ReLU(),nn.Conv1d(8,4,3,padding=1),nn.ReLU())
            self.dec=nn.Sequential(nn.Conv1d(4,8,3,padding=1),nn.ReLU(),nn.Conv1d(8,1,3,padding=1))
        def forward(self,x): return self.dec(self.enc(x.unsqueeze(1))).squeeze(1)

    if key == "vae": model = VAE()
    elif key == "cae": model = CAE()
    else: key="ae"; model = AE()
    opt=torch.optim.Adam(model.parameters(),lr=.003)
    history=[]; max_epochs=max(20,min(int(epochs),600))
    model.train()
    for ep in range(max_epochs):
        opt.zero_grad()
        if key=="vae":
            recon,mu,lv=model(Xtr); mse=((recon-Xtr)**2).mean(); kld=-.5*torch.mean(1+lv-mu.pow(2)-lv.exp()); loss=mse+1e-3*kld
        else:
            recon=model(Xtr); loss=((recon-Xtr)**2).mean()
        loss.backward(); opt.step()
        if ep % max(1,max_epochs//20)==0 or ep==max_epochs-1: history.append({"epoch":ep+1,"loss":_f(loss.item())})
    model.eval()
    with torch.no_grad():
        if key=="vae": rec,_,_=model(Xte)
        else: rec=model(Xte)
        per=((rec-Xte)**2).mean(dim=1).cpu().numpy()
        trrec=model(Xtr)[0] if key=="vae" else model(Xtr)
        train_err=((trrec-Xtr)**2).mean(dim=1).cpu().numpy()
    threshold=float(np.quantile(train_err,.95)); anomaly=(per>threshold)
    preview=[]; times=list(data.index)[w-1:]
    test_times=times[split:]
    for t,e,a in zip(test_times[-100:],per[-100:],anomaly[-100:]): preview.append({"time":str(t),"reconstruction_mse":_f(e),"anomaly":bool(a)})
    return {
        "analysis":"deep_autoencoder", "model_type":key, "dependent":dependent, "time_variable":time_variable,
        "n_windows":int(len(X)), "train_windows":int(len(Xtr)), "test_windows":int(len(Xte)), "window":w, "latent_dim":ld,
        "metrics":{"test_reconstruction_mse":_f(float(np.mean(per))),"anomaly_threshold_95pct_train":_f(threshold),"test_anomaly_count":int(anomaly.sum()),"test_anomaly_rate":_f(float(anomaly.mean()))},
        "training_history":history, "anomaly_preview":preview,
        "diagnostics":{"chronological_split":True,"scaled_on_observed_series":True,"data_boundary":"Reconstructions and any latent simulations are model outputs only and must never be represented as observed research data.","overfit_check":"Compare chronological training and test reconstruction errors and inspect anomaly stability under alternative windows/latent dimensions."},
    }


def run_prophet_adapter(df, dependent: str, time_variable: str, horizon: int = 12) -> dict[str, Any]:
    if not _available("prophet"):
        raise RuntimeError("Prophet analysis requires the optional prophet runtime from requirements-advanced-ml.txt.")
    import pandas as pd
    from prophet import Prophet
    work=df[[time_variable,dependent]].copy(); work[time_variable]=pd.to_datetime(work[time_variable],errors="coerce"); work[dependent]=pd.to_numeric(work[dependent],errors="coerce"); work=work.dropna().sort_values(time_variable)
    if len(work)<30: raise ValueError("Prophet requires at least 30 usable ordered observations in ProjectReady.")
    train=work.rename(columns={time_variable:"ds",dependent:"y"}); m=Prophet(); m.fit(train)
    # Infer median observed cadence without inventing a calendar frequency.
    deltas=train["ds"].sort_values().diff().dropna(); delta=deltas.median() if not deltas.empty else pd.Timedelta(days=1)
    future=pd.DataFrame({"ds":[train["ds"].iloc[-1]+delta*(i+1) for i in range(max(1,int(horizon)))]})
    fc=m.predict(future)
    return {"analysis":"hybrid_forecasting","model_type":"prophet","n":int(len(train)),"horizon":int(horizon),"forecast":[{"time":str(r.ds),"forecast":_f(r.yhat),"lower":_f(r.yhat_lower),"upper":_f(r.yhat_upper)} for r in fc.itertuples()],"diagnostics":{"changepoints":[str(x) for x in getattr(m,"changepoints",[])],"note":"Use rolling-origin validation against naive/statistical baselines before accepting forecast superiority."}}


def run_neuralforecast_adapter(df, dependent: str, time_variable: str, model_type: str = "nbeats", lags: int = 24, horizon: int = 12) -> dict[str, Any]:
    if not _available("neuralforecast"):
        raise RuntimeError("N-BEATS/N-HiTS analysis requires the optional neuralforecast runtime from requirements-advanced-ml.txt.")
    import pandas as pd
    from neuralforecast import NeuralForecast
    from neuralforecast.models import NBEATS, NHITS
    work=df[[time_variable,dependent]].copy(); work[time_variable]=pd.to_datetime(work[time_variable],errors="coerce"); work[dependent]=pd.to_numeric(work[dependent],errors="coerce"); work=work.dropna().sort_values(time_variable)
    if len(work)<max(50,2*int(lags)+int(horizon)): raise ValueError("N-BEATS/N-HiTS needs more ordered observations for the chosen context and horizon.")
    nfdf=pd.DataFrame({"unique_id":"series_1","ds":work[time_variable],"y":work[dependent]})
    h=max(1,int(horizon)); inp=max(h+1,int(lags)); key=str(model_type).lower()
    model=NHITS(h=h,input_size=inp,max_steps=300) if key in {"nhits","n-hits"} else NBEATS(h=h,input_size=inp,max_steps=300)
    nf=NeuralForecast(models=[model],freq=pd.infer_freq(nfdf["ds"]) or "D"); nf.fit(df=nfdf); pred=nf.predict().reset_index()
    value_cols=[c for c in pred.columns if c not in {"unique_id","ds","cutoff"}]
    value_col=value_cols[0] if value_cols else None
    return {"analysis":"deep_forecasting","model_type":"nhits" if key in {"nhits","n-hits"} else "nbeats","n":int(len(work)),"horizon":h,"forecast":[{"time":str(r["ds"]),"forecast":_f(r[value_col]) if value_col else None} for _,r in pred.iterrows()],"diagnostics":{"training_max_steps":300,"chronological_model":True,"note":"Compare against naive/statistical baselines and use rolling-origin validation for publication claims."}}


def run_timegpt_adapter(df, dependent: str, time_variable: str, horizon: int = 12) -> dict[str, Any]:
    if not _available("nixtla") or not (os.getenv("TIMEGPT_API_KEY") or os.getenv("NIXTLA_API_KEY")):
        raise RuntimeError("TimeGPT requires the optional nixtla runtime and a configured TIMEGPT_API_KEY/NIXTLA_API_KEY.")
    import pandas as pd
    from nixtla import NixtlaClient
    work=df[[time_variable,dependent]].copy(); work[time_variable]=pd.to_datetime(work[time_variable],errors="coerce"); work[dependent]=pd.to_numeric(work[dependent],errors="coerce"); work=work.dropna().sort_values(time_variable)
    client=NixtlaClient(api_key=os.getenv("TIMEGPT_API_KEY") or os.getenv("NIXTLA_API_KEY"))
    frame=work.rename(columns={time_variable:"ds",dependent:"y"}); frame["unique_id"]="series_1"
    fc=client.forecast(df=frame,h=max(1,int(horizon)),time_col="ds",target_col="y",id_col="unique_id")
    predcol=next((c for c in fc.columns if str(c).lower() in {"timegpt","forecast","yhat"}),None)
    if predcol is None: predcol=next((c for c in fc.columns if c not in {"unique_id","ds"}),None)
    return {"analysis":"foundation_forecasting","model_type":"timegpt","n":int(len(work)),"horizon":int(horizon),"forecast":[{"time":str(r["ds"]),"forecast":_f(r[predcol]) if predcol else None} for _,r in fc.iterrows()],"diagnostics":{"external_service":True,"data_transfer_notice":"This adapter sends the configured series to the external TimeGPT service. Institutional/data-governance approval remains the researcher's responsibility.","validation_required":"Backtest against local statistical and naive baselines."}}


def run_advanced_forecasting_adapter(df, dependent: str, time_variable: str, model_type: str, lags: int = 24, horizon: int = 12, epochs: int = 120) -> dict[str, Any]:
    key=str(model_type or "").lower()
    if key in {"ae","vae","cae"}: return run_torch_autoencoder(df,dependent,time_variable,key,lags,epochs)
    if key=="prophet": return run_prophet_adapter(df,dependent,time_variable,horizon)
    if key in {"nbeats","n-beats","nhits","n-hits"}: return run_neuralforecast_adapter(df,dependent,time_variable,key,lags,horizon)
    if key=="timegpt": return run_timegpt_adapter(df,dependent,time_variable,horizon)
    # PatchTST/Informer/Autoformer/DeepAR/Chronos/TimesFM and NeuralProphet are
    # exposed through exact capability gates. Never silently substitute another
    # model and label it as the requested architecture.
    return deep_capability(key)
