"""
Multi-Agent Financial Scenario Planner
Three-agent system: forecasting agent (ARIMA + exponential smoothing),
risk agent (sensitivity analysis + VaR-style tail risk), and
narrative agent (Claude API). Sequential handoffs via shared state object.
"""

import json
import uuid
import anthropic
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, Callable
from datetime import datetime
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.stattools import adfuller
from scipy import stats
from fastapi import FastAPI
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Shared state object — agents communicate through this
# ---------------------------------------------------------------------------

@dataclass
class PlanningState:
    session_id: str
    created_at: str
    organization: str
    planning_horizon_months: int
    historical_data: Optional[pd.DataFrame] = None

    # Populated by ForecastingAgent
    demand_forecast: Optional[np.ndarray] = None
    revenue_forecast: Optional[np.ndarray] = None
    forecast_confidence_lower: Optional[np.ndarray] = None
    forecast_confidence_upper: Optional[np.ndarray] = None
    forecast_model_used: Optional[str] = None
    forecast_mape: Optional[float] = None

    # Populated by RiskAgent
    scenarios: Optional[dict] = None          # {name: {metric: [values]}}
    var_95: Optional[float] = None
    cvar_95: Optional[float] = None
    sensitivity_rankings: Optional[list] = None
    downside_probability: Optional[float] = None
    stress_test_results: Optional[dict] = None

    # Populated by NarrativeAgent
    executive_report: Optional[str] = None
    key_decisions: Optional[list] = None
    scenario_comparison: Optional[str] = None

    # Agent trace (audit log)
    agent_trace: list[dict] = field(default_factory=list)

    def log(self, agent: str, action: str, detail: str = ""):
        self.agent_trace.append({
            "agent": agent, "action": action, "detail": detail,
            "timestamp": datetime.utcnow().isoformat(),
        })


# ---------------------------------------------------------------------------
# Agent 1: Forecasting Agent
# ---------------------------------------------------------------------------

class ForecastingAgent:
    name = "ForecastingAgent"

    def _select_model(self, series: pd.Series) -> str:
        adf = adfuller(series.dropna())
        is_stationary = adf[1] < 0.05
        has_seasonality = len(series) >= 24
        if has_seasonality:
            return "holtwinters"
        return "arima_stationary" if is_stationary else "arima_differenced"

    def _fit_arima(self, series: pd.Series, horizon: int) -> tuple:
        adf = adfuller(series.dropna())
        d = 0 if adf[1] < 0.05 else 1
        model = ARIMA(series, order=(2, d, 2))
        fitted = model.fit()
        forecast_obj = fitted.get_forecast(steps=horizon)
        forecast = forecast_obj.predicted_mean.values
        ci = forecast_obj.conf_int()
        return forecast, ci.iloc[:, 0].values, ci.iloc[:, 1].values, "ARIMA"

    def _fit_holtwinters(self, series: pd.Series, horizon: int) -> tuple:
        period = min(12, len(series) // 2)
        model = ExponentialSmoothing(
            series,
            trend="add",
            seasonal="add" if len(series) >= period * 2 else None,
            seasonal_periods=period,
        )
        fitted = model.fit(optimized=True)
        forecast = fitted.forecast(horizon)
        # Approximate CI using historical residuals
        resid_std = fitted.resid.std()
        z = stats.norm.ppf(0.975)
        horizon_arr = np.arange(1, horizon + 1)
        ci_half = z * resid_std * np.sqrt(horizon_arr)
        return forecast.values, forecast.values - ci_half, forecast.values + ci_half, "HoltWinters"

    def _compute_mape(self, actuals: pd.Series, model_name: str) -> float:
        n = min(12, len(actuals) // 3)
        train, test = actuals.iloc[:-n], actuals.iloc[-n:]
        try:
            if model_name == "HoltWinters":
                f, _, _, _ = self._fit_holtwinters(train, n)
            else:
                f, _, _, _ = self._fit_arima(train, n)
            return float(np.mean(np.abs((test.values - f) / np.maximum(np.abs(test.values), 1e-6))))
        except Exception:
            return float("nan")

    def run(self, state: PlanningState) -> PlanningState:
        state.log(self.name, "start", f"Horizon: {state.planning_horizon_months} months")
        df = state.historical_data

        demand_series = df["demand"].dropna()
        revenue_series = df["revenue"].dropna()

        model_type = self._select_model(revenue_series)
        state.log(self.name, "model_selection", f"Selected: {model_type}")

        if model_type == "holtwinters":
            d_fc, d_lower, d_upper, label = self._fit_holtwinters(
                demand_series, state.planning_horizon_months
            )
            r_fc, r_lower, r_upper, _ = self._fit_holtwinters(
                revenue_series, state.planning_horizon_months
            )
        else:
            d_fc, d_lower, d_upper, label = self._fit_arima(
                demand_series, state.planning_horizon_months
            )
            r_fc, r_lower, r_upper, _ = self._fit_arima(
                revenue_series, state.planning_horizon_months
            )

        mape = self._compute_mape(revenue_series, label)

        state.demand_forecast = d_fc
        state.revenue_forecast = r_fc
        state.forecast_confidence_lower = r_lower
        state.forecast_confidence_upper = r_upper
        state.forecast_model_used = label
        state.forecast_mape = mape

        state.log(self.name, "complete",
                  f"Model: {label}, MAPE: {mape:.3f}, "
                  f"12m revenue forecast: {r_fc[-1]:,.0f}")
        return state


# ---------------------------------------------------------------------------
# Agent 2: Risk Agent
# ---------------------------------------------------------------------------

class RiskAgent:
    name = "RiskAgent"
    N_SIMULATIONS = 5000

    STRESS_SCENARIOS = {
        "demand_shock_20pct": {"demand_multiplier": 0.80, "cost_multiplier": 1.0},
        "cost_inflation_15pct": {"demand_multiplier": 1.0, "cost_multiplier": 1.15},
        "combined_downside": {"demand_multiplier": 0.85, "cost_multiplier": 1.10},
        "severe_recession": {"demand_multiplier": 0.65, "cost_multiplier": 1.20},
    }

    def _sensitivity_analysis(self, state: PlanningState) -> list[dict]:
        base_revenue = state.revenue_forecast.mean()
        df = state.historical_data
        inputs = {
            "demand": df["demand"].values,
            "cost_per_unit": df.get("cost_per_unit", pd.Series(np.ones(len(df)))).values,
            "price": (df["revenue"] / df["demand"].replace(0, np.nan)).fillna(0).values,
        }
        sensitivities = []
        for var_name, values in inputs.items():
            if len(values) < 3:
                continue
            r, p = stats.pearsonr(values[-len(state.revenue_forecast):] if
                                   len(values) >= len(state.revenue_forecast)
                                   else np.resize(values, len(state.revenue_forecast)),
                                   state.revenue_forecast)
            sensitivities.append({
                "variable": var_name,
                "correlation_with_revenue": round(float(r), 3),
                "p_value": round(float(p), 4),
                "significant": float(p) < 0.05,
            })
        return sorted(sensitivities, key=lambda x: abs(x["correlation_with_revenue"]), reverse=True)

    def _monte_carlo_revenue(self, state: PlanningState) -> np.ndarray:
        rng = np.random.default_rng(42)
        base = state.revenue_forecast.mean()
        uncertainty = (state.forecast_confidence_upper - state.forecast_confidence_lower).mean() / 4
        draws = rng.normal(base, uncertainty, self.N_SIMULATIONS)
        return draws

    def _var_cvar(self, distribution: np.ndarray, confidence: float = 0.95) -> tuple:
        var = float(np.percentile(distribution, (1 - confidence) * 100))
        cvar = float(distribution[distribution <= var].mean()) if (distribution <= var).any() else var
        return var, cvar

    def _run_stress_tests(self, state: PlanningState) -> dict:
        results = {}
        base_revenue = state.revenue_forecast.sum()
        for scenario_name, params in self.STRESS_SCENARIOS.items():
            stressed_revenue = (
                base_revenue
                * params["demand_multiplier"]
                / params["cost_multiplier"]
            )
            results[scenario_name] = {
                "total_revenue": round(stressed_revenue, 0),
                "revenue_impact": round(stressed_revenue - base_revenue, 0),
                "impact_pct": round((stressed_revenue - base_revenue) / base_revenue * 100, 1),
                "demand_multiplier": params["demand_multiplier"],
                "cost_multiplier": params["cost_multiplier"],
            }
        return results

    def run(self, state: PlanningState) -> PlanningState:
        state.log(self.name, "start")
        assert state.revenue_forecast is not None, "ForecastingAgent must run first"

        mc_distribution = self._monte_carlo_revenue(state)
        var_95, cvar_95 = self._var_cvar(mc_distribution)
        downside_prob = float((mc_distribution < state.revenue_forecast.mean() * 0.90).mean())
        sensitivity = self._sensitivity_analysis(state)
        stress_tests = self._run_stress_tests(state)

        state.var_95 = var_95
        state.cvar_95 = cvar_95
        state.downside_probability = downside_prob
        state.sensitivity_rankings = sensitivity
        state.stress_test_results = stress_tests
        state.scenarios = {
            "monte_carlo": {
                "p10": float(np.percentile(mc_distribution, 10)),
                "p50": float(np.percentile(mc_distribution, 50)),
                "p90": float(np.percentile(mc_distribution, 90)),
            }
        }

        state.log(self.name, "complete",
                  f"VaR(95%): {var_95:,.0f}, Downside prob: {downside_prob:.1%}")
        return state


# ---------------------------------------------------------------------------
# Agent 3: Narrative Agent
# ---------------------------------------------------------------------------

class NarrativeAgent:
    name = "NarrativeAgent"

    SYSTEM_PROMPT = """You are a CFO-level financial planning analyst. Given outputs from a
forecasting agent and risk assessment agent, write an executive scenario planning report.
The audience is C-suite and board members. Be direct, quantitative, and action-oriented.

Return valid JSON:
{
  "executive_report": "4-5 paragraph narrative covering: forecast outlook, key risks, stress scenarios, recommended actions",
  "key_decisions": ["decision point 1", "decision point 2", "decision point 3"],
  "scenario_comparison": "2-3 sentence comparison of upside vs downside scenarios"
}"""

    def run(self, state: PlanningState) -> PlanningState:
        state.log(self.name, "start")
        client = anthropic.Anthropic()

        stress_summary = "\n".join(
            f"  {name}: impact {v['impact_pct']:+.1f}% (${v['revenue_impact']:,.0f})"
            for name, v in (state.stress_test_results or {}).items()
        )
        sensitivity_top = (state.sensitivity_rankings or [])[:3]

        user_content = (
            f"Organization: {state.organization}\n"
            f"Planning horizon: {state.planning_horizon_months} months\n\n"
            f"FORECAST:\n"
            f"  Model: {state.forecast_model_used} (MAPE={state.forecast_mape:.3f})\n"
            f"  Revenue forecast (sum): ${state.revenue_forecast.sum():,.0f}\n"
            f"  Confidence range: ${state.forecast_confidence_lower.sum():,.0f} — "
            f"${state.forecast_confidence_upper.sum():,.0f}\n\n"
            f"RISK:\n"
            f"  VaR (95%): ${state.var_95:,.0f}\n"
            f"  CVaR (95%): ${state.cvar_95:,.0f}\n"
            f"  Downside probability (>10% miss): {state.downside_probability:.1%}\n"
            f"  Monte Carlo P10/P50/P90: "
            f"${state.scenarios['monte_carlo']['p10']:,.0f} / "
            f"${state.scenarios['monte_carlo']['p50']:,.0f} / "
            f"${state.scenarios['monte_carlo']['p90']:,.0f}\n\n"
            f"STRESS TESTS:\n{stress_summary}\n\n"
            f"TOP SENSITIVITY DRIVERS:\n" +
            "\n".join(f"  {s['variable']}: r={s['correlation_with_revenue']}"
                      for s in sensitivity_top)
        )

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1200,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip().lstrip("```json").rstrip("```").strip()
        parsed = json.loads(raw)

        state.executive_report = parsed.get("executive_report", "")
        state.key_decisions = parsed.get("key_decisions", [])
        state.scenario_comparison = parsed.get("scenario_comparison", "")

        state.log(self.name, "complete", "Executive report generated")
        return state


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class FinancialPlannerOrchestrator:
    def __init__(self):
        self.agents: list[Callable] = [
            ForecastingAgent().run,
            RiskAgent().run,
            NarrativeAgent().run,
        ]

    def run(self, historical_df: pd.DataFrame, organization: str,
            horizon_months: int = 12) -> PlanningState:
        state = PlanningState(
            session_id=str(uuid.uuid4()),
            created_at=datetime.utcnow().isoformat(),
            organization=organization,
            planning_horizon_months=horizon_months,
            historical_data=historical_df,
        )

        for agent_fn in self.agents:
            agent_name = agent_fn.__self__.name
            print(f"Running {agent_name}...")
            state = agent_fn(state)

        return state


# ---------------------------------------------------------------------------
# FastAPI interface
# ---------------------------------------------------------------------------

app = FastAPI()

class PlanningRequest(BaseModel):
    organization: str
    horizon_months: int = 12
    historical_data: dict     # {column: {index: value}}

@app.post("/plan")
def run_planning(req: PlanningRequest):
    df = pd.DataFrame(req.historical_data)
    orchestrator = FinancialPlannerOrchestrator()
    state = orchestrator.run(df, req.organization, req.horizon_months)
    return {
        "session_id": state.session_id,
        "executive_report": state.executive_report,
        "key_decisions": state.key_decisions,
        "scenario_comparison": state.scenario_comparison,
        "forecast_model": state.forecast_model_used,
        "var_95": state.var_95,
        "stress_tests": state.stress_test_results,
        "agent_trace": state.agent_trace,
    }


if __name__ == "__main__":
    np.random.seed(42)
    months = 36
    dates = pd.date_range("2022-01-01", periods=months, freq="MS")
    historical_df = pd.DataFrame({
        "demand": 5000 + np.linspace(0, 1200, months) + np.random.normal(0, 150, months),
        "revenue": 750000 + np.linspace(0, 180000, months) + np.random.normal(0, 20000, months),
        "cost_per_unit": np.random.normal(95, 5, months),
    }, index=dates)

    orchestrator = FinancialPlannerOrchestrator()
    state = orchestrator.run(historical_df, "Acme Health Systems", horizon_months=12)

    print(f"\nSession: {state.session_id}")
    print(f"Forecast model: {state.forecast_model_used} (MAPE={state.forecast_mape:.3f})")
    print(f"VaR (95%): ${state.var_95:,.0f}")
    print(f"\nAgent trace:")
    for entry in state.agent_trace:
        print(f"  [{entry['agent']}] {entry['action']}: {entry['detail']}")
    print(f"\nExecutive Report:\n{state.executive_report}")
