"""
Automated EDA & Data Quality Report Agent
Dataset profiling: distributions, missingness (MCAR/MAR/MNAR classification),
outlier detection via Isolation Forest and IQR, correlation and redundancy analysis,
cardinality assessment. Issues ranked by modeling impact severity.
"""

import json
import anthropic
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from scipy import stats
from sklearn.ensemble import IsolationForest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import roc_auc_score
from fastapi import FastAPI, UploadFile
from pydantic import BaseModel
import io


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ISOLATION_FOREST_CONTAMINATION = 0.05
HIGH_CARDINALITY_THRESHOLD = 0.50     # unique ratio above this = high cardinality
HIGH_CORRELATION_THRESHOLD = 0.85     # Pearson r above this = redundant feature
SKEWNESS_THRESHOLD = 2.0
KURTOSIS_THRESHOLD = 7.0
MISSING_MAR_AUC_THRESHOLD = 0.65     # AUC above this classifies as MAR (not MCAR)
MISSING_MNAR_CORRELATION_THRESHOLD = 0.20
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

SEVERITY_SCORES = {"critical": 3, "warning": 2, "info": 1}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ColumnProfile:
    name: str
    dtype: str
    n_unique: int
    unique_ratio: float
    missing_count: int
    missing_pct: float
    missingness_class: str           # "MCAR" | "MAR" | "MNAR" | "none"
    outlier_count: int
    outlier_method: str              # "IQR" | "isolation_forest" | "both" | "none"
    skewness: Optional[float]
    kurtosis: Optional[float]
    mean: Optional[float]
    median: Optional[float]
    std: Optional[float]
    p1: Optional[float]
    p99: Optional[float]
    top_values: Optional[list]
    issues: list[dict] = field(default_factory=list)   # [{severity, message, recommendation}]

@dataclass
class CorrelationFlag:
    col_a: str
    col_b: str
    correlation: float
    severity: str
    recommendation: str

@dataclass
class QualityReport:
    dataset_shape: tuple
    column_profiles: list[ColumnProfile]
    correlation_flags: list[CorrelationFlag]
    overall_severity: str
    issue_summary: dict              # {critical: N, warning: N, info: N}
    preprocessing_recommendations: list[dict]
    narrative: str


# ---------------------------------------------------------------------------
# Distribution profiling
# ---------------------------------------------------------------------------

def profile_numeric(series: pd.Series) -> dict:
    clean = series.dropna()
    if len(clean) == 0:
        return {}
    return {
        "mean": float(clean.mean()),
        "median": float(clean.median()),
        "std": float(clean.std()),
        "skewness": float(clean.skew()),
        "kurtosis": float(clean.kurtosis()),
        "p1": float(clean.quantile(0.01)),
        "p99": float(clean.quantile(0.99)),
    }


def profile_categorical(series: pd.Series) -> dict:
    vc = series.value_counts()
    return {
        "top_values": vc.head(10).to_dict(),
        "entropy": float(stats.entropy(vc.values / vc.sum())),
    }


# ---------------------------------------------------------------------------
# Missingness classification: MCAR / MAR / MNAR
# ---------------------------------------------------------------------------

def classify_missingness(df: pd.DataFrame, col: str) -> str:
    if df[col].isna().sum() == 0:
        return "none"

    missing_indicator = df[col].isna().astype(int)

    # Test for MAR: can missingness be predicted from other columns?
    other_numeric = df.select_dtypes(include="number").drop(columns=[col], errors="ignore")
    other_numeric = other_numeric.fillna(other_numeric.median())
    if len(other_numeric.columns) >= 2 and missing_indicator.sum() >= 10:
        try:
            clf = LogisticRegression(max_iter=300, random_state=42)
            clf.fit(other_numeric, missing_indicator)
            auc = roc_auc_score(missing_indicator, clf.predict_proba(other_numeric)[:, 1])
            if auc > MISSING_MAR_AUC_THRESHOLD:
                return "MAR"
        except Exception:
            pass

    # Test for MNAR: missingness correlated with the column's own values
    non_missing = df.loc[df[col].notna(), col]
    missing_rows = df.index[df[col].isna()]
    if len(missing_rows) > 5 and df[col].dtype in ["float64", "int64"]:
        below_median = (non_missing < non_missing.median()).sum()
        above_median = (non_missing >= non_missing.median()).sum()
        mnar_ratio = abs(below_median - above_median) / max(len(non_missing), 1)
        if mnar_ratio > MISSING_MNAR_CORRELATION_THRESHOLD:
            return "MNAR"

    return "MCAR"


# ---------------------------------------------------------------------------
# Outlier detection
# ---------------------------------------------------------------------------

def detect_outliers_iqr(series: pd.Series) -> np.ndarray:
    clean = series.dropna()
    q1, q3 = clean.quantile(0.25), clean.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return ((series < lower) | (series > upper)).values


def detect_outliers_isolation_forest(df: pd.DataFrame,
                                      numeric_cols: list[str]) -> np.ndarray:
    X = df[numeric_cols].fillna(df[numeric_cols].median())
    if len(X) < 20 or X.shape[1] == 0:
        return np.zeros(len(df), dtype=bool)
    iso = IsolationForest(
        contamination=ISOLATION_FOREST_CONTAMINATION,
        random_state=42, n_jobs=-1
    )
    predictions = iso.fit_predict(X)
    return predictions == -1


# ---------------------------------------------------------------------------
# Correlation & redundancy analysis
# ---------------------------------------------------------------------------

def detect_high_correlations(df: pd.DataFrame,
                              threshold: float = HIGH_CORRELATION_THRESHOLD) -> list[CorrelationFlag]:
    numeric = df.select_dtypes(include="number")
    if numeric.shape[1] < 2:
        return []
    corr = numeric.corr(method="pearson").abs()
    flags = []
    for i, col_a in enumerate(corr.columns):
        for col_b in corr.columns[i + 1:]:
            r = corr.loc[col_a, col_b]
            if r >= threshold:
                severity = "critical" if r >= 0.95 else "warning"
                flags.append(CorrelationFlag(
                    col_a=col_a,
                    col_b=col_b,
                    correlation=float(r),
                    severity=severity,
                    recommendation=(
                        f"Consider dropping one of '{col_a}' or '{col_b}' — "
                        f"Pearson r={r:.3f} indicates near-perfect redundancy."
                        if r >= 0.95 else
                        f"High correlation between '{col_a}' and '{col_b}' (r={r:.3f}). "
                        f"Consider PCA or dropping one for linear models."
                    ),
                ))
    return flags


# ---------------------------------------------------------------------------
# Issue generation
# ---------------------------------------------------------------------------

def build_column_issues(profile: dict, col: str, dtype: str,
                         outlier_count: int, outlier_pct: float,
                         missingness_class: str, missing_pct: float,
                         unique_ratio: float) -> list[dict]:
    issues = []

    # Missing values
    if missing_pct > 0.50:
        issues.append({"severity": "critical",
                        "message": f"{missing_pct:.1%} missing values — unusable for most models",
                        "recommendation": f"Drop column or impute with domain knowledge; "
                                          f"missingness pattern: {missingness_class}"})
    elif missing_pct > 0.15:
        strat = {"MCAR": "mean/median imputation", "MAR": "model-based imputation (KNN or MissForest)",
                 "MNAR": "flag + model-based imputation — missingness is informative"}.get(
            missingness_class, "investigate before imputing")
        issues.append({"severity": "warning",
                        "message": f"{missing_pct:.1%} missing ({missingness_class})",
                        "recommendation": strat})

    # High cardinality
    if dtype == "object" and unique_ratio > HIGH_CARDINALITY_THRESHOLD:
        issues.append({"severity": "warning",
                        "message": f"High cardinality: {unique_ratio:.1%} unique values",
                        "recommendation": "Consider target encoding, embedding, or grouping rare levels"})

    # Outliers
    if outlier_pct > 0.10:
        issues.append({"severity": "critical",
                        "message": f"{outlier_pct:.1%} outliers detected",
                        "recommendation": "Investigate data source; consider winsorization or log transform"})
    elif outlier_pct > 0.03:
        issues.append({"severity": "warning",
                        "message": f"{outlier_pct:.1%} outliers",
                        "recommendation": "Apply IQR-based clipping or robust scaling"})

    # Distribution shape
    if dtype in ["float64", "int64"]:
        skew = profile.get("skewness", 0) or 0
        kurt = profile.get("kurtosis", 0) or 0
        if abs(skew) > SKEWNESS_THRESHOLD:
            issues.append({"severity": "warning",
                            "message": f"Highly skewed (skewness={skew:.2f})",
                            "recommendation": "Apply log1p or Box-Cox transform for tree/linear models"})
        if kurt > KURTOSIS_THRESHOLD:
            issues.append({"severity": "info",
                            "message": f"Heavy-tailed distribution (kurtosis={kurt:.2f})",
                            "recommendation": "Robust scaling (RobustScaler) recommended"})

    return issues


# ---------------------------------------------------------------------------
# Full profiling pipeline
# ---------------------------------------------------------------------------

def profile_dataset(df: pd.DataFrame) -> QualityReport:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    categorical_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

    iso_flags = detect_outliers_isolation_forest(df, numeric_cols) if numeric_cols else np.zeros(len(df), dtype=bool)

    column_profiles = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        n_unique = int(df[col].nunique())
        unique_ratio = n_unique / max(len(df), 1)
        missing_count = int(df[col].isna().sum())
        missing_pct = missing_count / max(len(df), 1)
        missingness_class = classify_missingness(df, col)

        iqr_flags = detect_outliers_iqr(df[col]) if col in numeric_cols else np.zeros(len(df), dtype=bool)
        outlier_combined = iqr_flags | iso_flags
        outlier_count = int(outlier_combined.sum())
        outlier_pct = outlier_count / max(len(df), 1)
        outlier_method = (
            "both" if iqr_flags.any() and iso_flags.any() else
            "IQR" if iqr_flags.any() else
            "isolation_forest" if iso_flags.any() else "none"
        )

        numeric_stats = profile_numeric(df[col]) if col in numeric_cols else {}
        cat_stats = profile_categorical(df[col]) if col in categorical_cols else {}

        issues = build_column_issues(
            numeric_stats, col, dtype, outlier_count, outlier_pct,
            missingness_class, missing_pct, unique_ratio
        )

        column_profiles.append(ColumnProfile(
            name=col, dtype=dtype, n_unique=n_unique, unique_ratio=unique_ratio,
            missing_count=missing_count, missing_pct=missing_pct,
            missingness_class=missingness_class,
            outlier_count=outlier_count, outlier_method=outlier_method,
            skewness=numeric_stats.get("skewness"),
            kurtosis=numeric_stats.get("kurtosis"),
            mean=numeric_stats.get("mean"),
            median=numeric_stats.get("median"),
            std=numeric_stats.get("std"),
            p1=numeric_stats.get("p1"),
            p99=numeric_stats.get("p99"),
            top_values=list(cat_stats.get("top_values", {}).keys())[:5],
            issues=sorted(issues, key=lambda x: SEVERITY_SCORES.get(x["severity"], 0), reverse=True),
        ))

    corr_flags = detect_high_correlations(df)

    all_issues = [iss for cp in column_profiles for iss in cp.issues]
    issue_summary = {
        "critical": sum(1 for i in all_issues if i["severity"] == "critical"),
        "warning": sum(1 for i in all_issues if i["severity"] == "warning"),
        "info": sum(1 for i in all_issues if i["severity"] == "info"),
    }
    overall_severity = (
        "critical" if issue_summary["critical"] > 0 else
        "warning" if issue_summary["warning"] > 0 else "info"
    )

    preprocessing_recommendations = sorted(
        [iss for iss in all_issues],
        key=lambda x: SEVERITY_SCORES.get(x["severity"], 0),
        reverse=True,
    )[:10]

    narrative = generate_narrative(df, column_profiles, corr_flags, issue_summary)

    return QualityReport(
        dataset_shape=df.shape,
        column_profiles=column_profiles,
        correlation_flags=corr_flags,
        overall_severity=overall_severity,
        issue_summary=issue_summary,
        preprocessing_recommendations=preprocessing_recommendations,
        narrative=narrative,
    )


# ---------------------------------------------------------------------------
# Claude API narrative
# ---------------------------------------------------------------------------

NARRATIVE_PROMPT = """You are a senior data scientist reviewing an automated data quality report.
Summarize the key findings in 3-4 sentences for a technical audience.
Focus on: what will most impact modeling quality, what needs immediate attention,
and what can be deferred. Be specific and actionable."""

def generate_narrative(df: pd.DataFrame, profiles: list[ColumnProfile],
                        corr_flags: list[CorrelationFlag], summary: dict) -> str:
    client = anthropic.Anthropic()
    critical_cols = [
        f"{p.name} ({', '.join(i['message'] for i in p.issues if i['severity'] == 'critical')})"
        for p in profiles if any(i["severity"] == "critical" for i in p.issues)
    ]
    user_content = (
        f"Dataset: {df.shape[0]} rows × {df.shape[1]} columns\n"
        f"Issue summary: {summary}\n"
        f"Critical columns: {critical_cols[:5]}\n"
        f"High correlations: {len(corr_flags)} pairs above threshold\n"
        f"Overall missing rate: {df.isna().mean().mean():.1%}"
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=400,
        system=NARRATIVE_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# FastAPI interface
# ---------------------------------------------------------------------------

app = FastAPI()

@app.post("/profile")
async def profile_upload(file: UploadFile):
    content = await file.read()
    df = pd.read_csv(io.BytesIO(content))
    report = profile_dataset(df)
    return {
        "shape": report.dataset_shape,
        "overall_severity": report.overall_severity,
        "issue_summary": report.issue_summary,
        "narrative": report.narrative,
        "columns": [
            {"name": p.name, "issues": p.issues[:3], "missing_pct": p.missing_pct,
             "outlier_count": p.outlier_count, "missingness_class": p.missingness_class}
            for p in report.column_profiles
        ],
        "high_correlations": [
            {"col_a": f.col_a, "col_b": f.col_b, "r": f.correlation, "severity": f.severity}
            for f in report.correlation_flags
        ],
    }


if __name__ == "__main__":
    np.random.seed(42)
    n = 1000
    df = pd.DataFrame({
        "age": np.random.normal(45, 15, n),
        "income": np.exp(np.random.normal(10.5, 0.8, n)),   # lognormal
        "score": np.random.uniform(0, 100, n),
        "category": np.random.choice(["A", "B", "C", "D"], n, p=[0.6, 0.25, 0.10, 0.05]),
        "high_card_id": [f"ID_{i:05d}" for i in range(n)],
        "redundant_age": None,
    })
    df["redundant_age"] = df["age"] * 1.02 + np.random.normal(0, 0.5, n)  # near-duplicate

    # Introduce missing values
    df.loc[np.random.choice(n, 150, replace=False), "income"] = np.nan
    df.loc[np.random.choice(n, 30, replace=False), "score"] = np.nan

    # Introduce outliers
    df.loc[np.random.choice(n, 20, replace=False), "age"] = np.random.uniform(150, 200, 20)

    report = profile_dataset(df)
    print(f"Dataset: {report.dataset_shape[0]} rows × {report.dataset_shape[1]} columns")
    print(f"Overall severity: {report.overall_severity.upper()}")
    print(f"Issues: {report.issue_summary}")
    print(f"\nTop issues:")
    for rec in report.preprocessing_recommendations[:5]:
        print(f"  [{rec['severity'].upper()}] {rec['message']}")
    print(f"\nHigh correlations: {len(report.correlation_flags)}")
    for cf in report.correlation_flags:
        print(f"  {cf.col_a} ↔ {cf.col_b}: r={cf.correlation:.3f} [{cf.severity}]")
