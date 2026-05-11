"""
A/B Test Interpreter Agent
Sequential validity checks: SRM detection, peeking bias correction via mSPRT,
novelty effect flagging, Cohen's d + CATE for practical significance.
Claude API synthesizes findings into a recommendation memo.
"""

import json
import anthropic
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from scipy import stats
from scipy.stats import chi2_contingency


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SRM_ALPHA = 0.01                   # strict threshold for sample ratio mismatch
MSRPT_ALPHA = 0.05                 # always-valid inference significance level
MSRPT_V_STAR = 0.5                 # mSPRT tuning parameter (prior variance)
NOVELTY_WINDOW_DAYS = 7            # days to exclude for novelty effect check
MIN_SAMPLE_PER_ARM = 100
PRACTICAL_SIGNIFICANCE_THRESHOLD = 0.05  # minimum detectable Cohen's d
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExperimentData:
    experiment_id: str
    metric_name: str
    control_values: np.ndarray
    treatment_values: np.ndarray
    control_timestamps: Optional[pd.Series] = None
    treatment_timestamps: Optional[pd.Series] = None
    expected_split: float = 0.5            # expected fraction in control
    experiment_start: Optional[str] = None
    experiment_end: Optional[str] = None
    covariates: Optional[pd.DataFrame] = None

@dataclass
class ValidityCheck:
    name: str
    passed: bool
    severity: str                          # "error" | "warning" | "info"
    detail: str
    stat: Optional[float] = None
    p_value: Optional[float] = None

@dataclass
class InterpretationResult:
    experiment_id: str
    validity_checks: list[ValidityCheck]
    is_valid: bool
    statistical_significance: bool
    practical_significance: bool
    effect_size_cohens_d: float
    ate: float
    ate_ci_lower: float
    ate_ci_upper: float
    p_value: float
    msrpt_significant: bool
    novelty_effect_detected: bool
    recommendation: str                    # "ship" | "do_not_ship" | "inconclusive" | "extend"
    memo: str


# ---------------------------------------------------------------------------
# Validity check 1: Sample Ratio Mismatch (SRM)
# ---------------------------------------------------------------------------

def check_srm(n_control: int, n_treatment: int,
              expected_split: float = 0.5) -> ValidityCheck:
    n_total = n_control + n_treatment
    expected_control = n_total * expected_split
    expected_treatment = n_total * (1 - expected_split)

    chi2, p_value = chi2_contingency(
        [[n_control, n_treatment],
         [expected_control, expected_treatment]]
    )[:2]

    passed = p_value >= SRM_ALPHA
    return ValidityCheck(
        name="Sample Ratio Mismatch",
        passed=passed,
        severity="error" if not passed else "info",
        detail=(
            f"SRM detected: observed {n_control}/{n_treatment} "
            f"(expected {expected_split:.0%}/{1-expected_split:.0%}). "
            f"χ²={chi2:.2f}, p={p_value:.4f}. Assignment mechanism may be biased."
            if not passed else
            f"No SRM detected. Split: {n_control}/{n_treatment} (χ²={chi2:.2f}, p={p_value:.3f})"
        ),
        stat=chi2,
        p_value=p_value,
    )


# ---------------------------------------------------------------------------
# Validity check 2: Minimum sample size
# ---------------------------------------------------------------------------

def check_sample_size(n_control: int, n_treatment: int) -> ValidityCheck:
    min_n = min(n_control, n_treatment)
    passed = min_n >= MIN_SAMPLE_PER_ARM
    return ValidityCheck(
        name="Minimum Sample Size",
        passed=passed,
        severity="warning" if not passed else "info",
        detail=(
            f"Underpowered: smallest arm has {min_n} samples (minimum: {MIN_SAMPLE_PER_ARM}). "
            f"Results may not generalize."
            if not passed else
            f"Adequate sample size: control={n_control}, treatment={n_treatment}"
        ),
    )


# ---------------------------------------------------------------------------
# Validity check 3: mSPRT — always-valid sequential testing (peeking correction)
# ---------------------------------------------------------------------------

def msrpt_test(control: np.ndarray, treatment: np.ndarray,
               v_star: float = MSRPT_V_STAR,
               alpha: float = MSRPT_ALPHA) -> tuple[bool, float, float]:
    """
    Mixture Sequential Probability Ratio Test (mSPRT).
    Provides valid inference regardless of when you look at the data (no peeking bias).
    Returns (significant, e_value, threshold).
    """
    n_c, n_t = len(control), len(treatment)
    mu_c, mu_t = control.mean(), treatment.mean()
    sigma_pool = np.sqrt((control.var() * (n_c - 1) + treatment.var() * (n_t - 1))
                         / (n_c + n_t - 2))

    if sigma_pool == 0:
        return False, 1.0, 1.0 / alpha

    delta_hat = mu_t - mu_c
    n_harm = 2 * n_c * n_t / (n_c + n_t)     # harmonic mean sample size

    # mSPRT e-value (Wald-type mixture over normal prior with variance v_star)
    t_stat = delta_hat / (sigma_pool * np.sqrt(2 / n_harm))
    e_value = np.sqrt(1 + n_harm * v_star / sigma_pool**2) * np.exp(
        (n_harm * v_star * t_stat**2) / (2 * (sigma_pool**2 + n_harm * v_star))
    )
    threshold = 1.0 / alpha
    return bool(e_value >= threshold), float(e_value), float(threshold)


def check_peeking_bias(control: np.ndarray, treatment: np.ndarray) -> ValidityCheck:
    significant, e_val, threshold = msrpt_test(control, treatment)
    # Compare with naive t-test to detect peeking discrepancy
    _, naive_p = stats.ttest_ind(control, treatment)
    naive_sig = naive_p < 0.05

    discrepancy = naive_sig and not significant
    return ValidityCheck(
        name="Peeking Bias (mSPRT)",
        passed=not discrepancy,
        severity="warning" if discrepancy else "info",
        detail=(
            f"Potential peeking bias: naive t-test is significant (p={naive_p:.4f}) "
            f"but mSPRT e-value={e_val:.2f} < threshold={threshold:.1f}. "
            f"Result may not be valid under sequential testing."
            if discrepancy else
            f"mSPRT e-value={e_val:.2f} (threshold={threshold:.1f}). "
            f"Result is valid under always-valid sequential testing."
        ),
        stat=e_val,
        p_value=None,
    )


# ---------------------------------------------------------------------------
# Validity check 4: Novelty effect detection
# ---------------------------------------------------------------------------

def check_novelty_effect(treatment_values: np.ndarray,
                          treatment_timestamps: Optional[pd.Series],
                          window_days: int = NOVELTY_WINDOW_DAYS) -> ValidityCheck:
    if treatment_timestamps is None or len(treatment_timestamps) == 0:
        return ValidityCheck(
            name="Novelty Effect",
            passed=True,
            severity="info",
            detail="No timestamps provided — novelty effect check skipped.",
        )

    ts = pd.to_datetime(treatment_timestamps)
    start = ts.min()
    cutoff = start + pd.Timedelta(days=window_days)

    early_mask = ts <= cutoff
    late_mask = ts > cutoff

    if early_mask.sum() < 10 or late_mask.sum() < 10:
        return ValidityCheck(
            name="Novelty Effect",
            passed=True,
            severity="info",
            detail="Insufficient data for novelty effect check.",
        )

    early = treatment_values[early_mask.values]
    late = treatment_values[late_mask.values]
    t_stat, p_value = stats.ttest_ind(early, late)
    decay = float(early.mean() - late.mean())
    detected = p_value < 0.05 and decay > 0

    return ValidityCheck(
        name="Novelty Effect",
        passed=not detected,
        severity="warning" if detected else "info",
        detail=(
            f"Novelty effect detected: early treatment mean={early.mean():.3f} vs "
            f"late={late.mean():.3f} (decay={decay:+.3f}, p={p_value:.4f}). "
            f"True long-term effect is likely lower than observed ATE."
            if detected else
            f"No significant novelty effect. Early vs. late treatment means: "
            f"{early.mean():.3f} vs {late.mean():.3f} (p={p_value:.3f})"
        ),
        stat=t_stat,
        p_value=p_value,
    )


# ---------------------------------------------------------------------------
# Statistical and practical significance
# ---------------------------------------------------------------------------

def compute_effect(control: np.ndarray, treatment: np.ndarray) -> dict:
    ate = float(treatment.mean() - control.mean())
    pooled_std = np.sqrt((control.var() + treatment.var()) / 2)
    cohens_d = ate / pooled_std if pooled_std > 0 else 0.0

    n_c, n_t = len(control), len(treatment)
    se = np.sqrt(control.var() / n_c + treatment.var() / n_t)
    ci_lower = ate - 1.96 * se
    ci_upper = ate + 1.96 * se
    _, p_value = stats.ttest_ind(control, treatment)

    return {
        "ate": ate,
        "cohens_d": float(cohens_d),
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "p_value": float(p_value),
        "statistical_significance": p_value < 0.05,
        "practical_significance": abs(cohens_d) >= PRACTICAL_SIGNIFICANCE_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# Recommendation logic
# ---------------------------------------------------------------------------

def determine_recommendation(checks: list[ValidityCheck], effect: dict,
                               msrpt_sig: bool, novelty: bool) -> str:
    has_errors = any(c.severity == "error" and not c.passed for c in checks)
    if has_errors:
        return "inconclusive"
    if not effect["statistical_significance"] or not msrpt_sig:
        n_total = sum(c.stat or 0 for c in checks if c.name == "Minimum Sample Size")
        return "extend"
    if not effect["practical_significance"]:
        return "do_not_ship"
    if novelty:
        return "extend"
    if effect["ate"] > 0:
        return "ship"
    return "do_not_ship"


# ---------------------------------------------------------------------------
# Claude API memo synthesis
# ---------------------------------------------------------------------------

MEMO_PROMPT = """You are an expert statistician writing an experiment recommendation memo
for a non-technical leadership team. Given experiment validity checks, effect size estimates,
and a recommendation, write a clear, concise decision memo (max 300 words).

Include: what the experiment tested, what happened statistically, whether to act, and why.
Avoid jargon. Be direct about uncertainty if it exists."""

def generate_memo(exp: ExperimentData, checks: list[ValidityCheck],
                  effect: dict, recommendation: str) -> str:
    client = anthropic.Anthropic()
    checks_text = "\n".join(
        f"  [{c.severity.upper()}] {c.name}: {'PASS' if c.passed else 'FAIL'} — {c.detail}"
        for c in checks
    )
    user_content = (
        f"Experiment: {exp.experiment_id}\n"
        f"Metric: {exp.metric_name}\n"
        f"Sample: control n={len(exp.control_values)}, treatment n={len(exp.treatment_values)}\n\n"
        f"Validity checks:\n{checks_text}\n\n"
        f"Effect: ATE={effect['ate']:+.4f}, Cohen's d={effect['cohens_d']:.3f}, "
        f"95% CI=[{effect['ci_lower']:+.4f}, {effect['ci_upper']:+.4f}], "
        f"p={effect['p_value']:.4f}\n\n"
        f"Recommendation: {recommendation.upper()}"
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=500,
        system=MEMO_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(exp: ExperimentData) -> InterpretationResult:
    checks: list[ValidityCheck] = []

    checks.append(check_sample_size(len(exp.control_values), len(exp.treatment_values)))
    checks.append(check_srm(len(exp.control_values), len(exp.treatment_values), exp.expected_split))
    checks.append(check_peeking_bias(exp.control_values, exp.treatment_values))
    checks.append(check_novelty_effect(exp.treatment_values, exp.treatment_timestamps))

    effect = compute_effect(exp.control_values, exp.treatment_values)
    msrpt_sig, _, _ = msrpt_test(exp.control_values, exp.treatment_values)
    novelty_detected = not checks[-1].passed

    recommendation = determine_recommendation(checks, effect, msrpt_sig, novelty_detected)
    is_valid = not any(c.severity == "error" and not c.passed for c in checks)

    memo = generate_memo(exp, checks, effect, recommendation)

    return InterpretationResult(
        experiment_id=exp.experiment_id,
        validity_checks=checks,
        is_valid=is_valid,
        statistical_significance=effect["statistical_significance"],
        practical_significance=effect["practical_significance"],
        effect_size_cohens_d=effect["cohens_d"],
        ate=effect["ate"],
        ate_ci_lower=effect["ci_lower"],
        ate_ci_upper=effect["ci_upper"],
        p_value=effect["p_value"],
        msrpt_significant=msrpt_sig,
        novelty_effect_detected=novelty_detected,
        recommendation=recommendation,
        memo=memo,
    )


if __name__ == "__main__":
    np.random.seed(42)
    n = 800
    control = np.random.normal(0.42, 0.12, n)
    treatment = np.random.normal(0.45, 0.12, n)
    timestamps = pd.date_range("2025-01-01", periods=n, freq="h")

    exp = ExperimentData(
        experiment_id="EXP-2025-014",
        metric_name="conversion_rate",
        control_values=control,
        treatment_values=treatment,
        control_timestamps=timestamps[:n],
        treatment_timestamps=timestamps[:n],
        expected_split=0.5,
        experiment_start="2025-01-01",
    )

    result = run_pipeline(exp)
    print(f"Recommendation: {result.recommendation.upper()}")
    print(f"ATE: {result.ate:+.4f}, Cohen's d: {result.effect_size_cohens_d:.3f}")
    print(f"\nValidity checks:")
    for c in result.validity_checks:
        status = "PASS" if c.passed else "FAIL"
        print(f"  [{c.severity.upper()}] {c.name}: {status}")
    print(f"\nMemo:\n{result.memo}")
