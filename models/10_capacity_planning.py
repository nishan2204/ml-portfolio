"""
Capacity Planning Simulation
Monte Carlo simulation engine replacing point-estimate capacity decisions
with probabilistic scenario planning. Outputs confidence intervals,
break-even thresholds, and tail-risk quantiles.
"""

import json
import numpy as np
import pandas as pd
import anthropic
from dataclasses import dataclass, field
from typing import Optional
from scipy import stats
from scipy.linalg import cholesky


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

N_ITERATIONS = 10_000
RANDOM_SEED = 42
CONFIDENCE_LEVELS = [0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]
VAR_CONFIDENCE = 0.95           # VaR tail confidence
CLAUDE_MODEL = "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DistributionSpec:
    """Parameterizes a random variable in the simulation."""
    name: str
    dist: str                   # "normal" | "lognormal" | "uniform" | "triangular" | "beta"
    params: dict                # distribution-specific parameters
    unit: str = ""

@dataclass
class CapacityScenario:
    name: str
    demand_growth_pct: DistributionSpec
    cost_per_unit: DistributionSpec
    utilization_rate: DistributionSpec
    fixed_costs: DistributionSpec
    revenue_per_unit: DistributionSpec
    correlation_matrix: Optional[np.ndarray] = None  # correlate demand & revenue draws

@dataclass
class SimulationResult:
    scenario_name: str
    iterations: int
    # Capacity metrics
    net_revenue: np.ndarray
    utilization: np.ndarray
    break_even_capacity: np.ndarray
    # Summary stats
    mean_net_revenue: float
    median_net_revenue: float
    std_net_revenue: float
    var_95: float                       # Value at Risk at 95%
    cvar_95: float                      # Conditional VaR (expected shortfall)
    break_even_probability: float
    quantiles: dict                     # {0.10: val, 0.25: val, ...}
    # Sensitivity
    sensitivity: dict                   # variable -> Pearson r with net_revenue

@dataclass
class PlanningReport:
    scenarios: list[SimulationResult]
    narrative: str
    recommended_capacity: float
    key_risks: list[str]
    confidence_note: str


# ---------------------------------------------------------------------------
# Random draw engine
# ---------------------------------------------------------------------------

def draw_samples(spec: DistributionSpec, n: int, rng: np.random.Generator) -> np.ndarray:
    p = spec.params
    if spec.dist == "normal":
        return rng.normal(p["mean"], p["std"], n)
    elif spec.dist == "lognormal":
        return rng.lognormal(p["mean"], p["sigma"], n)
    elif spec.dist == "uniform":
        return rng.uniform(p["low"], p["high"], n)
    elif spec.dist == "triangular":
        return rng.triangular(p["left"], p["mode"], p["right"], n)
    elif spec.dist == "beta":
        return rng.beta(p["alpha"], p["beta"], n)
    else:
        raise ValueError(f"Unknown distribution: {spec.dist}")


def correlated_draws(specs: list[DistributionSpec], corr_matrix: np.ndarray,
                     n: int, rng: np.random.Generator) -> list[np.ndarray]:
    """
    Generate correlated samples via Cholesky decomposition.
    Draws uniform marginals, applies Cholesky correlation, then inverts CDFs.
    """
    k = len(specs)
    assert corr_matrix.shape == (k, k)

    L = cholesky(corr_matrix, lower=True)
    z = rng.standard_normal((k, n))
    corr_z = L @ z                     # correlated standard normals

    # Map to uniform via normal CDF, then invert each marginal's CDF
    uniforms = stats.norm.cdf(corr_z)
    samples = []
    for i, spec in enumerate(specs):
        p = spec.params
        if spec.dist == "normal":
            samples.append(stats.norm.ppf(uniforms[i], p["mean"], p["std"]))
        elif spec.dist == "lognormal":
            samples.append(np.exp(stats.norm.ppf(uniforms[i], p["mean"], p["sigma"])))
        elif spec.dist == "uniform":
            samples.append(stats.uniform.ppf(uniforms[i], p["low"], p["high"] - p["low"]))
        elif spec.dist == "triangular":
            samples.append(stats.triang.ppf(
                uniforms[i],
                c=(p["mode"] - p["left"]) / (p["right"] - p["left"]),
                loc=p["left"],
                scale=p["right"] - p["left"],
            ))
        else:
            samples.append(draw_samples(spec, n, rng))
    return samples


# ---------------------------------------------------------------------------
# Monte Carlo simulation
# ---------------------------------------------------------------------------

def run_simulation(scenario: CapacityScenario,
                   base_capacity: float,
                   n_iter: int = N_ITERATIONS) -> SimulationResult:
    rng = np.random.default_rng(RANDOM_SEED)

    if scenario.correlation_matrix is not None:
        specs = [scenario.demand_growth_pct, scenario.revenue_per_unit]
        demand_growth, revenue_per_unit = correlated_draws(
            specs, scenario.correlation_matrix, n_iter, rng
        )
    else:
        demand_growth = draw_samples(scenario.demand_growth_pct, n_iter, rng)
        revenue_per_unit = draw_samples(scenario.revenue_per_unit, n_iter, rng)

    cost_per_unit = draw_samples(scenario.cost_per_unit, n_iter, rng)
    utilization = draw_samples(scenario.utilization_rate, n_iter, rng).clip(0, 1)
    fixed_costs = draw_samples(scenario.fixed_costs, n_iter, rng)

    # Simulation model
    effective_capacity = base_capacity * (1 + demand_growth / 100)
    units_served = effective_capacity * utilization
    gross_revenue = units_served * revenue_per_unit
    variable_costs = units_served * cost_per_unit
    net_revenue = gross_revenue - variable_costs - fixed_costs

    # Break-even capacity: units needed to cover fixed costs
    margin_per_unit = (revenue_per_unit - cost_per_unit).clip(0.01)
    break_even = fixed_costs / margin_per_unit

    # Risk metrics
    losses = net_revenue[net_revenue < 0]
    var_95 = float(np.percentile(net_revenue, (1 - VAR_CONFIDENCE) * 100))
    cvar_95 = float(losses.mean()) if len(losses) > 0 else 0.0
    break_even_prob = float((net_revenue > 0).mean())

    quantiles = {str(q): float(np.quantile(net_revenue, q)) for q in CONFIDENCE_LEVELS}

    # Sensitivity: Pearson correlation of each input with net revenue
    sensitivity = {
        "demand_growth": float(np.corrcoef(demand_growth, net_revenue)[0, 1]),
        "revenue_per_unit": float(np.corrcoef(revenue_per_unit, net_revenue)[0, 1]),
        "cost_per_unit": float(np.corrcoef(cost_per_unit, net_revenue)[0, 1]),
        "utilization": float(np.corrcoef(utilization, net_revenue)[0, 1]),
        "fixed_costs": float(np.corrcoef(fixed_costs, net_revenue)[0, 1]),
    }

    return SimulationResult(
        scenario_name=scenario.name,
        iterations=n_iter,
        net_revenue=net_revenue,
        utilization=utilization,
        break_even_capacity=break_even,
        mean_net_revenue=float(net_revenue.mean()),
        median_net_revenue=float(np.median(net_revenue)),
        std_net_revenue=float(net_revenue.std()),
        var_95=var_95,
        cvar_95=cvar_95,
        break_even_probability=break_even_prob,
        quantiles=quantiles,
        sensitivity=sensitivity,
    )


# ---------------------------------------------------------------------------
# Claude API — narrative synthesis
# ---------------------------------------------------------------------------

PLANNING_PROMPT = """You are a strategic planning analyst. Given Monte Carlo simulation results
for multiple capacity scenarios, synthesize the findings into an executive briefing.
Focus on: key tradeoffs between scenarios, tail risks, the recommended capacity level, and
what assumptions drive the most uncertainty.

Return valid JSON:
{
  "narrative": "4-5 sentence executive narrative",
  "recommended_capacity_rationale": "2-3 sentence rationale",
  "key_risks": ["risk 1", "risk 2", "risk 3"],
  "confidence_note": "1 sentence on main source of uncertainty"
}"""

def synthesize_narrative(results: list[SimulationResult],
                          base_capacity: float) -> dict:
    client = anthropic.Anthropic()

    scenarios_text = "\n\n".join(
        f"Scenario: {r.scenario_name}\n"
        f"  Mean net revenue: ${r.mean_net_revenue:,.0f}\n"
        f"  Median: ${r.median_net_revenue:,.0f} | Std: ${r.std_net_revenue:,.0f}\n"
        f"  VaR (95%): ${r.var_95:,.0f} | CVaR (95%): ${r.cvar_95:,.0f}\n"
        f"  Break-even probability: {r.break_even_probability:.1%}\n"
        f"  P10/P50/P90: ${r.quantiles['0.1']:,.0f} / "
        f"${r.quantiles['0.5']:,.0f} / ${r.quantiles['0.9']:,.0f}\n"
        f"  Top sensitivity driver: "
        f"{max(r.sensitivity, key=lambda k: abs(r.sensitivity[k]))}"
        for r in results
    )

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=800,
        system=PLANNING_PROMPT,
        messages=[{"role": "user", "content":
                   f"Base capacity: {base_capacity:,.0f} units\n\n{scenarios_text}"}],
    )
    raw = response.content[0].text.strip().lstrip("```json").rstrip("```").strip()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(scenarios: list[CapacityScenario],
                 base_capacity: float) -> PlanningReport:
    results = []
    for scenario in scenarios:
        print(f"Simulating: {scenario.name} ({N_ITERATIONS:,} iterations)...")
        result = run_simulation(scenario, base_capacity)
        results.append(result)
        print(f"  Break-even probability: {result.break_even_probability:.1%}")
        print(f"  VaR (95%): ${result.var_95:,.0f}")

    print("\nSynthesizing narrative...")
    synthesis = synthesize_narrative(results, base_capacity)

    recommended_capacity = base_capacity * (
        1 + max(r.quantiles["0.5"] for r in results) /
        (base_capacity * max(r.mean_net_revenue / base_capacity for r in results))
    )

    return PlanningReport(
        scenarios=results,
        narrative=synthesis.get("narrative", ""),
        recommended_capacity=recommended_capacity,
        key_risks=synthesis.get("key_risks", []),
        confidence_note=synthesis.get("confidence_note", ""),
    )


# ---------------------------------------------------------------------------
# Example scenarios
# ---------------------------------------------------------------------------

BASE_SCENARIO = CapacityScenario(
    name="Base Case",
    demand_growth_pct=DistributionSpec("demand_growth", "normal", {"mean": 8.0, "std": 3.0}, "%"),
    cost_per_unit=DistributionSpec("cost", "lognormal", {"mean": 4.8, "sigma": 0.15}, "$"),
    utilization_rate=DistributionSpec("utilization", "beta", {"alpha": 7, "beta": 3}),
    fixed_costs=DistributionSpec("fixed_costs", "normal", {"mean": 2_500_000, "std": 200_000}, "$"),
    revenue_per_unit=DistributionSpec("revenue", "triangular",
                                       {"left": 130, "mode": 155, "right": 190}, "$"),
    correlation_matrix=np.array([[1.0, 0.45], [0.45, 1.0]]),  # demand & revenue correlated
)

BEAR_SCENARIO = CapacityScenario(
    name="Downside",
    demand_growth_pct=DistributionSpec("demand_growth", "normal", {"mean": 2.0, "std": 4.0}, "%"),
    cost_per_unit=DistributionSpec("cost", "lognormal", {"mean": 5.1, "sigma": 0.20}, "$"),
    utilization_rate=DistributionSpec("utilization", "beta", {"alpha": 5, "beta": 4}),
    fixed_costs=DistributionSpec("fixed_costs", "normal", {"mean": 2_800_000, "std": 300_000}, "$"),
    revenue_per_unit=DistributionSpec("revenue", "triangular",
                                       {"left": 115, "mode": 135, "right": 160}, "$"),
)

BULL_SCENARIO = CapacityScenario(
    name="Upside",
    demand_growth_pct=DistributionSpec("demand_growth", "normal", {"mean": 15.0, "std": 4.0}, "%"),
    cost_per_unit=DistributionSpec("cost", "lognormal", {"mean": 4.6, "sigma": 0.10}, "$"),
    utilization_rate=DistributionSpec("utilization", "beta", {"alpha": 9, "beta": 2}),
    fixed_costs=DistributionSpec("fixed_costs", "normal", {"mean": 2_400_000, "std": 150_000}, "$"),
    revenue_per_unit=DistributionSpec("revenue", "triangular",
                                       {"left": 150, "mode": 175, "right": 210}, "$"),
    correlation_matrix=np.array([[1.0, 0.60], [0.60, 1.0]]),
)


if __name__ == "__main__":
    BASE_CAPACITY = 50_000  # units per year

    report = run_pipeline([BASE_SCENARIO, BEAR_SCENARIO, BULL_SCENARIO], BASE_CAPACITY)

    print(f"\n{'='*60}")
    print(f"CAPACITY PLANNING REPORT")
    print(f"{'='*60}")
    print(f"\n{report.narrative}")
    print(f"\nRecommended capacity: {report.recommended_capacity:,.0f} units")
    print(f"\nKey risks:")
    for r in report.key_risks:
        print(f"  • {r}")
    print(f"\n{report.confidence_note}")

    print(f"\nScenario summary:")
    for r in report.scenarios:
        print(f"\n  {r.scenario_name}")
        print(f"    P10 / P50 / P90: ${r.quantiles['0.1']:>12,.0f} / "
              f"${r.quantiles['0.5']:>12,.0f} / ${r.quantiles['0.9']:>12,.0f}")
        print(f"    Break-even prob: {r.break_even_probability:.1%}")
        print(f"    VaR (95%):       ${r.var_95:>12,.0f}")
