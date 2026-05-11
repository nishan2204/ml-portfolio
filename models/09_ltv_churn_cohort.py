"""
LTV & Churn Cohort Analyzer
Kaplan-Meier survival curves and Cox Proportional Hazards modeling per cohort.
Leading indicator identification via Granger causality. Segment-level intervention
recommendations based on historical response rates.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from lifelines import KaplanMeierFitter, CoxPHFitter, WeibullAFTFitter
from lifelines.statistics import logrank_test, multivariate_logrank_test
from statsmodels.tsa.stattools import grangercausalitytests
from statsmodels.tsa.stattools import adfuller
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score
from sklearn.ensemble import GradientBoostingClassifier
import warnings
warnings.filterwarnings("ignore")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CHURN_DEFINITION_DAYS = 90       # no visit in 90 days = churned
EARLY_WARNING_HORIZON_DAYS = 60  # surface at-risk cohorts this far before churn
GRANGER_MAX_LAGS = 4
GRANGER_SIGNIFICANCE = 0.10
COHORT_MIN_SIZE = 50             # minimum cohort size for reliable survival estimates
COX_PENALIZER = 0.1              # L2 regularization for Cox model
LTV_DISCOUNT_RATE = 0.10         # annual discount rate for LTV calculation


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CohortDefinition:
    cohort_id: str
    acquisition_channel: str
    acquisition_month: str       # "2023-01"
    behavioral_segment: str      # from upstream segmentation
    n_patients: int

@dataclass
class SurvivalResult:
    cohort_id: str
    median_survival_days: float
    survival_at_30d: float
    survival_at_60d: float
    survival_at_90d: float
    survival_at_180d: float
    kmf: KaplanMeierFitter        # fitted KMF object for plotting

@dataclass
class CohortRiskProfile:
    cohort_id: str
    survival: SurvivalResult
    cox_hazard_ratios: dict
    leading_indicators: list[str]
    predicted_churn_rate_60d: float
    recommended_intervention: str
    historical_response_rate: float
    ltv_trajectory: list[float]   # monthly LTV projection


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_patient_timeline(snowflake_conn, cohort_month: str) -> pd.DataFrame:
    query = f"""
        SELECT
            p.patient_id,
            p.acquisition_channel,
            p.acquisition_date,
            DATEDIFF('day', p.acquisition_date, COALESCE(c.churn_date, CURRENT_DATE)) AS duration_days,
            CASE WHEN c.churn_date IS NOT NULL THEN 1 ELSE 0 END AS churned,
            p.tenure_days,
            f.visit_frequency_30d,
            f.visit_frequency_90d,
            f.avg_days_between_visits,
            f.nps_score,
            f.service_diversity_score,
            f.digital_engagement_score,
            f.revenue_ltm,
            f.referral_count,
            f.days_since_last_visit
        FROM patients p
        LEFT JOIN churn_events c ON p.patient_id = c.patient_id
        JOIN behavioral_features f ON p.patient_id = f.patient_id
        WHERE DATE_TRUNC('month', p.acquisition_date) = '{cohort_month}'
    """
    return pd.read_sql(query, snowflake_conn)


def load_intervention_history(snowflake_conn) -> pd.DataFrame:
    query = """
        SELECT
            cohort_id,
            intervention_type,
            intervention_date,
            n_targeted,
            n_responded,
            response_rate,
            avg_ltv_lift
        FROM intervention_outcomes
        WHERE intervention_date >= DATEADD('month', -24, CURRENT_DATE)
    """
    return pd.read_sql(query, snowflake_conn)


# ---------------------------------------------------------------------------
# Kaplan-Meier survival analysis
# ---------------------------------------------------------------------------

def fit_kaplan_meier(df: pd.DataFrame, cohort_id: str) -> SurvivalResult:
    kmf = KaplanMeierFitter()
    kmf.fit(
        durations=df["duration_days"],
        event_observed=df["churned"],
        label=cohort_id,
    )

    def survival_at(t: int) -> float:
        try:
            return float(kmf.survival_function_at_times([t]).iloc[0])
        except Exception:
            return float("nan")

    return SurvivalResult(
        cohort_id=cohort_id,
        median_survival_days=float(kmf.median_survival_time_),
        survival_at_30d=survival_at(30),
        survival_at_60d=survival_at(60),
        survival_at_90d=survival_at(90),
        survival_at_180d=survival_at(180),
        kmf=kmf,
    )


def compare_cohort_survival(cohort_dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Log-rank test for pairwise cohort survival differences."""
    cohort_ids = list(cohort_dfs.keys())
    results = []
    for i, c1 in enumerate(cohort_ids):
        for c2 in cohort_ids[i + 1:]:
            df1, df2 = cohort_dfs[c1], cohort_dfs[c2]
            lr = logrank_test(
                df1["duration_days"], df2["duration_days"],
                event_observed_A=df1["churned"], event_observed_B=df2["churned"],
            )
            results.append({
                "cohort_a": c1, "cohort_b": c2,
                "test_statistic": lr.test_statistic,
                "p_value": lr.p_value,
                "significant": lr.p_value < 0.05,
            })
    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Cox Proportional Hazards
# ---------------------------------------------------------------------------

COX_FEATURES = [
    "visit_frequency_30d", "visit_frequency_90d", "avg_days_between_visits",
    "nps_score", "service_diversity_score", "digital_engagement_score",
    "revenue_ltm", "referral_count", "days_since_last_visit", "tenure_days",
]

def fit_cox_model(df: pd.DataFrame) -> tuple[CoxPHFitter, dict]:
    cox_df = df[COX_FEATURES + ["duration_days", "churned"]].dropna()

    # Scale continuous features
    scaler = StandardScaler()
    cox_df[COX_FEATURES] = scaler.fit_transform(cox_df[COX_FEATURES])

    cph = CoxPHFitter(penalizer=COX_PENALIZER)
    cph.fit(cox_df, duration_col="duration_days", event_col="churned",
            show_progress=False)

    hazard_ratios = {
        feat: {
            "hr": float(np.exp(cph.params_[feat])),
            "p_value": float(cph.summary["p"][feat]),
            "significant": float(cph.summary["p"][feat]) < 0.05,
        }
        for feat in COX_FEATURES
    }
    return cph, hazard_ratios


def predict_churn_probability(cph: CoxPHFitter, df: pd.DataFrame,
                               horizon_days: int = 60) -> np.ndarray:
    cox_df = df[COX_FEATURES].fillna(df[COX_FEATURES].median())
    scaler = StandardScaler()
    cox_df = pd.DataFrame(scaler.fit_transform(cox_df), columns=COX_FEATURES)
    survival_fns = cph.predict_survival_function(cox_df, times=[horizon_days])
    return 1 - survival_fns.iloc[0].values


# ---------------------------------------------------------------------------
# Granger causality — leading indicator identification
# ---------------------------------------------------------------------------

def find_leading_indicators(cohort_timeseries: pd.DataFrame,
                             churn_rate_col: str = "monthly_churn_rate",
                             max_lags: int = GRANGER_MAX_LAGS) -> list[str]:
    """
    Test which behavioral metrics Granger-cause the churn rate series.
    Returns metrics that are statistically leading indicators.
    """
    candidate_cols = [c for c in cohort_timeseries.columns
                      if c != churn_rate_col and cohort_timeseries[c].dtype in ["float64", "int64"]]

    target = cohort_timeseries[churn_rate_col].dropna()
    if len(target) < max_lags + 2:
        return []

    # Check stationarity; difference if needed
    adf = adfuller(target)
    if adf[1] > 0.05:
        target = target.diff().dropna()

    leading = []
    for col in candidate_cols:
        series = cohort_timeseries[col].dropna()
        if len(series) < max_lags + 2:
            continue
        adf_s = adfuller(series)
        if adf_s[1] > 0.05:
            series = series.diff().dropna()

        aligned = pd.concat([target, series], axis=1, join="inner").dropna()
        if len(aligned) < max_lags + 2:
            continue
        try:
            gc_results = grangercausalitytests(aligned, maxlag=max_lags, verbose=False)
            min_p = min(
                gc_results[lag][0]["ssr_ftest"][1]
                for lag in range(1, max_lags + 1)
            )
            if min_p < GRANGER_SIGNIFICANCE:
                leading.append(col)
        except Exception:
            continue
    return leading


# ---------------------------------------------------------------------------
# LTV projection
# ---------------------------------------------------------------------------

def project_ltv(cohort_df: pd.DataFrame, cph: CoxPHFitter,
                months: int = 24) -> list[float]:
    monthly_revenue = float(cohort_df["revenue_ltm"].mean() / 12)
    r = LTV_DISCOUNT_RATE / 12
    ltv_trajectory = []
    cumulative = 0.0
    for m in range(1, months + 1):
        survival_m = cph.predict_survival_function(
            cohort_df[COX_FEATURES].fillna(0).head(1),
            times=[m * 30],
        ).iloc[0, 0]
        discounted = monthly_revenue * survival_m / ((1 + r) ** m)
        cumulative += discounted
        ltv_trajectory.append(round(cumulative, 2))
    return ltv_trajectory


# ---------------------------------------------------------------------------
# Intervention recommendation
# ---------------------------------------------------------------------------

def recommend_intervention(cohort_id: str, churn_rate_60d: float,
                            leading_indicators: list[str],
                            intervention_history: pd.DataFrame) -> tuple[str, float]:
    if "days_since_last_visit" in leading_indicators and churn_rate_60d > 0.30:
        intervention = "reactivation_campaign"
    elif "nps_score" in leading_indicators:
        intervention = "satisfaction_recovery_outreach"
    elif "referral_count" in leading_indicators:
        intervention = "referral_incentive_program"
    else:
        intervention = "general_retention_nurture"

    history = intervention_history[
        intervention_history["intervention_type"] == intervention
    ]
    historical_response_rate = (
        float(history["response_rate"].mean()) if len(history) > 0 else 0.15
    )
    return intervention, historical_response_rate


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(cohort_dfs: dict[str, pd.DataFrame],
                 cohort_timeseries: dict[str, pd.DataFrame],
                 intervention_history: pd.DataFrame) -> list[CohortRiskProfile]:
    profiles = []

    for cohort_id, df in cohort_dfs.items():
        if len(df) < COHORT_MIN_SIZE:
            print(f"  Skipping {cohort_id}: insufficient sample (n={len(df)})")
            continue

        print(f"Analyzing cohort: {cohort_id} (n={len(df)})...")

        survival = fit_kaplan_meier(df, cohort_id)
        cph, hazard_ratios = fit_cox_model(df)
        churn_probs = predict_churn_probability(cph, df, horizon_days=EARLY_WARNING_HORIZON_DAYS)
        predicted_churn_rate = float(churn_probs.mean())

        ts = cohort_timeseries.get(cohort_id, pd.DataFrame())
        leading = find_leading_indicators(ts) if not ts.empty else []

        intervention, response_rate = recommend_intervention(
            cohort_id, predicted_churn_rate, leading, intervention_history
        )

        ltv = project_ltv(df, cph)

        profiles.append(CohortRiskProfile(
            cohort_id=cohort_id,
            survival=survival,
            cox_hazard_ratios=hazard_ratios,
            leading_indicators=leading,
            predicted_churn_rate_60d=predicted_churn_rate,
            recommended_intervention=intervention,
            historical_response_rate=response_rate,
            ltv_trajectory=ltv,
        ))

    profiles.sort(key=lambda p: p.predicted_churn_rate_60d, reverse=True)
    return profiles


if __name__ == "__main__":
    np.random.seed(42)
    n = 500

    def make_cohort_df(churn_rate: float = 0.25) -> pd.DataFrame:
        return pd.DataFrame({
            "duration_days": np.random.exponential(180, n),
            "churned": np.random.binomial(1, churn_rate, n),
            "visit_frequency_30d": np.random.poisson(3, n),
            "visit_frequency_90d": np.random.poisson(9, n),
            "avg_days_between_visits": np.random.exponential(30, n),
            "nps_score": np.random.normal(7, 2, n).clip(0, 10),
            "service_diversity_score": np.random.uniform(0, 1, n),
            "digital_engagement_score": np.random.uniform(0, 1, n),
            "revenue_ltm": np.random.normal(2400, 600, n),
            "referral_count": np.random.poisson(1, n),
            "days_since_last_visit": np.random.exponential(20, n),
            "tenure_days": np.random.randint(30, 730, n),
        })

    cohort_dfs = {
        "2023-Q1-organic": make_cohort_df(0.18),
        "2023-Q1-paid": make_cohort_df(0.32),
        "2023-Q2-referral": make_cohort_df(0.12),
    }
    intervention_history = pd.DataFrame({
        "cohort_id": ["2022-Q4"] * 3,
        "intervention_type": ["reactivation_campaign", "satisfaction_recovery_outreach",
                               "referral_incentive_program"],
        "intervention_date": ["2023-01-15"] * 3,
        "n_targeted": [200, 150, 100],
        "n_responded": [50, 45, 35],
        "response_rate": [0.25, 0.30, 0.35],
        "avg_ltv_lift": [180, 220, 310],
    })

    profiles = run_pipeline(cohort_dfs, {}, intervention_history)
    for p in profiles:
        print(f"\n{p.cohort_id}")
        print(f"  Median survival: {p.survival.median_survival_days:.0f} days")
        print(f"  Predicted churn (60d): {p.predicted_churn_rate_60d:.1%}")
        print(f"  Recommended intervention: {p.recommended_intervention}")
        print(f"  Historical response rate: {p.historical_response_rate:.1%}")
