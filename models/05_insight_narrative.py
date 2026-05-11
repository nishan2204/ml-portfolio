"""
Automated Insight Narrative Generator
Detects anomalies and trends in structured data, ranks signals by significance,
and synthesizes executive-ready narratives using the Claude API.
"""

import json
import anthropic
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from scipy import stats
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import acf
from fastapi import FastAPI
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ANOMALY_ZSCORE_THRESHOLD = 2.5
ANOMALY_IQR_MULTIPLIER = 1.8
MIN_EFFECT_SIZE = 0.3           # Cohen's d threshold for signal inclusion
MAX_SIGNALS_TO_NARRATIVE = 5
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1200


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Signal:
    metric: str
    signal_type: str            # "anomaly" | "trend" | "shift" | "seasonality_break"
    direction: str              # "spike" | "drop" | "increasing" | "decreasing"
    magnitude: float            # raw change
    effect_size: float          # Cohen's d or standardized effect
    p_value: float
    period: str                 # e.g. "2025-03" or "Week 12"
    context: str                # human-readable description
    rank: int = 0               # assigned after sorting

@dataclass
class NarrativeResult:
    signals: list[Signal]
    narrative: str
    executive_summary: str
    recommended_actions: list[str]
    data_period: str
    metrics_analyzed: int


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

def detect_zscore_anomalies(series: pd.Series, threshold: float = ANOMALY_ZSCORE_THRESHOLD,
                             metric_name: str = "") -> list[Signal]:
    mu, sigma = series.mean(), series.std()
    if sigma == 0:
        return []
    z_scores = (series - mu) / sigma
    signals = []
    for idx, z in z_scores.items():
        if abs(z) >= threshold:
            direction = "spike" if z > 0 else "drop"
            effect = abs(z)
            p_val = 2 * (1 - stats.norm.cdf(abs(z)))
            signals.append(Signal(
                metric=metric_name,
                signal_type="anomaly",
                direction=direction,
                magnitude=float(series[idx] - mu),
                effect_size=float(effect),
                p_value=float(p_val),
                period=str(idx),
                context=f"{metric_name} {direction} of {abs(series[idx] - mu):.2f} "
                        f"({z:+.1f} SD from mean) on {idx}",
            ))
    return signals


def detect_iqr_anomalies(series: pd.Series, multiplier: float = ANOMALY_IQR_MULTIPLIER,
                          metric_name: str = "") -> list[Signal]:
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - multiplier * iqr, q3 + multiplier * iqr
    signals = []
    for idx, val in series.items():
        if val < lower or val > upper:
            direction = "spike" if val > upper else "drop"
            magnitude = val - upper if val > upper else lower - val
            cohen_d = abs(val - series.mean()) / series.std() if series.std() > 0 else 0
            signals.append(Signal(
                metric=metric_name,
                signal_type="anomaly",
                direction=direction,
                magnitude=float(magnitude),
                effect_size=float(cohen_d),
                p_value=float(2 * (1 - stats.norm.cdf(cohen_d))),
                period=str(idx),
                context=f"{metric_name} outside IQR bounds ({direction}) on {idx}: "
                        f"value={val:.2f}, fence={'upper' if val > upper else 'lower'}={upper if val > upper else lower:.2f}",
            ))
    return signals


# ---------------------------------------------------------------------------
# Trend detection
# ---------------------------------------------------------------------------

def detect_trend(series: pd.Series, metric_name: str = "") -> Optional[Signal]:
    if len(series) < 4:
        return None
    x = np.arange(len(series))
    slope, intercept, r_value, p_value, std_err = stats.linregress(x, series.values)

    if p_value >= 0.10 or abs(r_value) < 0.4:
        return None

    pct_change = slope * len(series) / abs(series.mean()) * 100 if series.mean() != 0 else 0
    direction = "increasing" if slope > 0 else "decreasing"
    effect = abs(slope * len(series) / series.std()) if series.std() > 0 else 0

    return Signal(
        metric=metric_name,
        signal_type="trend",
        direction=direction,
        magnitude=float(slope * len(series)),
        effect_size=float(effect),
        p_value=float(p_value),
        period=f"{series.index[0]}–{series.index[-1]}",
        context=f"{metric_name} {direction} trend: {pct_change:+.1f}% over period "
                f"(slope={slope:.3f}, R²={r_value**2:.2f}, p={p_value:.3f})",
    )


def detect_level_shift(series: pd.Series, metric_name: str = "") -> Optional[Signal]:
    """Detect a structural break using Chow-style split-sample t-test."""
    if len(series) < 8:
        return None
    mid = len(series) // 2
    first_half = series.iloc[:mid]
    second_half = series.iloc[mid:]
    t_stat, p_value = stats.ttest_ind(first_half, second_half)
    if p_value >= 0.05:
        return None
    shift = second_half.mean() - first_half.mean()
    pooled_std = np.sqrt((first_half.std()**2 + second_half.std()**2) / 2)
    cohen_d = abs(shift) / pooled_std if pooled_std > 0 else 0
    direction = "increasing" if shift > 0 else "decreasing"
    return Signal(
        metric=metric_name,
        signal_type="shift",
        direction=direction,
        magnitude=float(shift),
        effect_size=float(cohen_d),
        p_value=float(p_value),
        period=str(series.index[mid]),
        context=f"{metric_name} structural level shift at {series.index[mid]}: "
                f"{shift:+.2f} mean change (Cohen's d={cohen_d:.2f})",
    )


# ---------------------------------------------------------------------------
# Seasonality break detection
# ---------------------------------------------------------------------------

def detect_seasonality_break(series: pd.Series, period: int = 12,
                              metric_name: str = "") -> Optional[Signal]:
    if len(series) < period * 2:
        return None
    try:
        decomp = seasonal_decompose(series, model="additive", period=period,
                                    extrapolate_trend="freq")
        seasonal_strength = decomp.seasonal.std() / series.std() if series.std() > 0 else 0
        if seasonal_strength < 0.15:
            return None
        recent_resid = decomp.resid.dropna().iloc[-period:]
        historical_resid = decomp.resid.dropna().iloc[:-period]
        t_stat, p_value = stats.ttest_ind(recent_resid, historical_resid)
        if p_value < 0.05:
            return Signal(
                metric=metric_name,
                signal_type="seasonality_break",
                direction="spike" if recent_resid.mean() > historical_resid.mean() else "drop",
                magnitude=float(recent_resid.mean() - historical_resid.mean()),
                effect_size=float(abs(t_stat)),
                p_value=float(p_value),
                period=str(series.index[-1]),
                context=f"{metric_name} seasonal pattern breaking: recent residuals deviate "
                        f"significantly from historical seasonal baseline (p={p_value:.3f})",
            )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Signal ranking
# ---------------------------------------------------------------------------

def rank_signals(signals: list[Signal], top_n: int = MAX_SIGNALS_TO_NARRATIVE) -> list[Signal]:
    scored = sorted(
        signals,
        key=lambda s: s.effect_size * (1 - s.p_value),
        reverse=True,
    )
    for i, s in enumerate(scored[:top_n]):
        s.rank = i + 1
    return scored[:top_n]


# ---------------------------------------------------------------------------
# Claude API narrative synthesis
# ---------------------------------------------------------------------------

NARRATIVE_SYSTEM_PROMPT = """You are an expert data analyst writing executive briefings.
Given a set of ranked statistical signals from a dataset, produce a polished narrative report.

Format your response as JSON:
{
  "executive_summary": "2–3 sentence summary of the most important findings",
  "narrative": "3–5 paragraph executive narrative connecting the signals into a coherent story",
  "recommended_actions": ["action 1", "action 2", "action 3"]
}

Write for a non-technical executive audience. Be specific, quantitative, and action-oriented.
Do not use jargon. Reference actual numbers from the signals."""


def synthesize_narrative(signals: list[Signal], context_metadata: dict) -> dict:
    client = anthropic.Anthropic()

    signals_text = "\n".join(
        f"[Signal {s.rank}] {s.context} | Effect size: {s.effect_size:.2f} | p={s.p_value:.4f}"
        for s in signals
    )
    user_content = (
        f"Dataset context: {json.dumps(context_metadata)}\n\n"
        f"Top signals (ranked by effect size × significance):\n{signals_text}"
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=MAX_TOKENS,
        system=NARRATIVE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip()
    cleaned = raw.lstrip("```json").rstrip("```").strip()
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(df: pd.DataFrame, metric_cols: list[str],
                 context_metadata: Optional[dict] = None) -> NarrativeResult:
    all_signals: list[Signal] = []

    for col in metric_cols:
        series = df[col].dropna()
        if len(series) < 4:
            continue

        all_signals.extend(detect_zscore_anomalies(series, metric_name=col))
        all_signals.extend(detect_iqr_anomalies(series, metric_name=col))

        trend = detect_trend(series, metric_name=col)
        if trend:
            all_signals.append(trend)

        shift = detect_level_shift(series, metric_name=col)
        if shift:
            all_signals.append(shift)

        if len(series) >= 24:
            sb = detect_seasonality_break(series, metric_name=col)
            if sb:
                all_signals.append(sb)

    # Filter by minimum effect size
    all_signals = [s for s in all_signals if s.effect_size >= MIN_EFFECT_SIZE]
    top_signals = rank_signals(all_signals)

    synthesis = synthesize_narrative(
        top_signals,
        context_metadata or {"period": str(df.index[-1]), "rows": len(df)},
    )

    return NarrativeResult(
        signals=top_signals,
        narrative=synthesis.get("narrative", ""),
        executive_summary=synthesis.get("executive_summary", ""),
        recommended_actions=synthesis.get("recommended_actions", []),
        data_period=f"{df.index[0]} – {df.index[-1]}",
        metrics_analyzed=len(metric_cols),
    )


# ---------------------------------------------------------------------------
# FastAPI interface
# ---------------------------------------------------------------------------

app = FastAPI()

class NarrativeRequest(BaseModel):
    data: dict            # {metric_name: {date: value, ...}, ...}
    context: Optional[dict] = None

@app.post("/generate")
def generate_narrative(req: NarrativeRequest):
    df = pd.DataFrame(req.data)
    df.index = pd.to_datetime(df.index)
    result = run_pipeline(df, list(df.columns), req.context)
    return {
        "executive_summary": result.executive_summary,
        "narrative": result.narrative,
        "recommended_actions": result.recommended_actions,
        "signals_detected": len(result.signals),
        "metrics_analyzed": result.metrics_analyzed,
    }


if __name__ == "__main__":
    np.random.seed(42)
    dates = pd.date_range("2023-01-01", periods=36, freq="MS")
    df = pd.DataFrame({
        "denial_rate": 0.12 + 0.02 * np.sin(np.linspace(0, 4 * np.pi, 36))
                       + np.random.normal(0, 0.005, 36),
        "revenue_per_visit": 850 + np.linspace(0, 120, 36) + np.random.normal(0, 20, 36),
        "no_show_rate": np.concatenate([
            np.random.normal(0.08, 0.01, 18),
            np.random.normal(0.14, 0.01, 18),  # level shift
        ]),
        "new_patient_volume": 200 + 30 * np.sin(np.linspace(0, 6 * np.pi, 36))
                              + np.random.normal(0, 8, 36),
    }, index=dates)

    result = run_pipeline(df, list(df.columns), {"organization": "Demo Health System"})
    print(f"Signals detected: {len(result.signals)}")
    print(f"\nExecutive Summary:\n{result.executive_summary}")
    print(f"\nTop signals:")
    for s in result.signals:
        print(f"  [{s.rank}] {s.context}")
