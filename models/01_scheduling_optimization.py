"""
Scheduling Optimization Engine
Staffing optimization across 25+ locations using CP-SAT constraint programming
with a genetic algorithm warm-start and SimPy simulation for validation.
"""

import random
import numpy as np
import simpy
from dataclasses import dataclass, field
from typing import Optional
from ortools.sat.python import cp_model
from fastapi import FastAPI
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Location:
    id: str
    name: str
    min_coverage: int          # minimum staff required at any time
    peak_windows: list[tuple]  # [(start_hour, end_hour), ...]
    skill_requirements: dict   # {"RN": 2, "Tech": 3, ...}

@dataclass
class Employee:
    id: str
    skills: list[str]
    preferred_shifts: list[int]   # preferred start hours
    max_hours_per_week: int = 40
    overtime_eligible: bool = True

@dataclass
class ShiftConfig:
    location_id: str
    start_hour: int
    duration_hours: int
    required_skills: dict
    min_staff: int
    max_staff: int


# ---------------------------------------------------------------------------
# Genetic algorithm — warm-start seed for CP-SAT
# ---------------------------------------------------------------------------

class GeneticScheduler:
    def __init__(self, employees: list[Employee], shifts: list[ShiftConfig],
                 population_size: int = 80, generations: int = 150):
        self.employees = employees
        self.shifts = shifts
        self.population_size = population_size
        self.generations = generations

    def _random_chromosome(self) -> dict:
        return {
            shift.location_id + str(shift.start_hour): random.sample(
                [e.id for e in self.employees
                 if any(s in e.skills for s in shift.required_skills)],
                k=min(shift.min_staff, len(self.employees))
            )
            for shift in self.shifts
        }

    def _fitness(self, chromosome: dict) -> float:
        score = 0.0
        for shift in self.shifts:
            key = shift.location_id + str(shift.start_hour)
            assigned = chromosome.get(key, [])
            coverage_gap = max(0, shift.min_staff - len(assigned))
            overtime_penalty = sum(
                1 for eid in assigned
                for e in self.employees if e.id == eid and not e.overtime_eligible
            )
            preference_score = sum(
                1 for eid in assigned
                for e in self.employees
                if e.id == eid and shift.start_hour in e.preferred_shifts
            )
            score += preference_score - 5 * coverage_gap - 2 * overtime_penalty
        return score

    def _crossover(self, parent_a: dict, parent_b: dict) -> dict:
        child = {}
        for key in parent_a:
            child[key] = parent_a[key] if random.random() < 0.5 else parent_b[key]
        return child

    def _mutate(self, chromosome: dict, rate: float = 0.05) -> dict:
        mutated = dict(chromosome)
        for shift in self.shifts:
            if random.random() < rate:
                key = shift.location_id + str(shift.start_hour)
                eligible = [e.id for e in self.employees
                            if any(s in e.skills for s in shift.required_skills)]
                if eligible:
                    mutated[key] = random.sample(
                        eligible, k=min(shift.min_staff, len(eligible))
                    )
        return mutated

    def run(self) -> dict:
        population = [self._random_chromosome() for _ in range(self.population_size)]
        for _ in range(self.generations):
            scored = sorted(population, key=self._fitness, reverse=True)
            elite = scored[:10]
            children = []
            while len(children) < self.population_size - len(elite):
                a, b = random.choices(elite, k=2)
                child = self._mutate(self._crossover(a, b))
                children.append(child)
            population = elite + children
        return max(population, key=self._fitness)


# ---------------------------------------------------------------------------
# CP-SAT solver — main optimizer
# ---------------------------------------------------------------------------

class CPSATScheduler:
    def __init__(self, employees: list[Employee], shifts: list[ShiftConfig],
                 warm_start: Optional[dict] = None):
        self.employees = employees
        self.shifts = shifts
        self.warm_start = warm_start
        self.model = cp_model.CpModel()
        self.solver = cp_model.CpSolver()
        self.solver.parameters.max_time_in_seconds = 480   # 8-minute batch window
        self.solver.parameters.num_search_workers = 8

    def build(self):
        n_emp = len(self.employees)
        n_shifts = len(self.shifts)

        # x[e][s] = 1 if employee e works shift s
        self.x = [
            [self.model.NewBoolVar(f'x_e{e}_s{s}') for s in range(n_shifts)]
            for e in range(n_emp)
        ]

        for s, shift in enumerate(self.shifts):
            # Coverage constraint: at least min_staff assigned
            self.model.Add(
                sum(self.x[e][s] for e in range(n_emp)) >= shift.min_staff
            )
            self.model.Add(
                sum(self.x[e][s] for e in range(n_emp)) <= shift.max_staff
            )
            # Skill constraint: assigned employees must have required skills
            for skill, count in shift.required_skills.items():
                self.model.Add(
                    sum(
                        self.x[e][s]
                        for e, emp in enumerate(self.employees)
                        if skill in emp.skills
                    ) >= count
                )

        for e, emp in enumerate(self.employees):
            # Hours constraint
            total_hours = sum(
                self.x[e][s] * self.shifts[s].duration_hours
                for s in range(n_shifts)
            )
            self.model.Add(total_hours <= emp.max_hours_per_week)

        # Objective: maximize preference alignment, minimize overtime
        preference_score = sum(
            self.x[e][s]
            for e, emp in enumerate(self.employees)
            for s, shift in enumerate(self.shifts)
            if shift.start_hour in emp.preferred_shifts
        )
        overtime_penalty = sum(
            self.x[e][s]
            for e, emp in enumerate(self.employees)
            for s in range(n_shifts)
            if not emp.overtime_eligible
        )
        self.model.Maximize(preference_score - 3 * overtime_penalty)

        # Warm-start hints from genetic algorithm
        if self.warm_start:
            for e, emp in enumerate(self.employees):
                for s, shift in enumerate(self.shifts):
                    key = shift.location_id + str(shift.start_hour)
                    hint = 1 if emp.id in self.warm_start.get(key, []) else 0
                    self.model.AddHint(self.x[e][s], hint)

    def solve(self) -> dict:
        self.build()
        status = self.solver.Solve(self.model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError("No feasible schedule found within time limit")

        assignments = {}
        for s, shift in enumerate(self.shifts):
            key = shift.location_id + str(shift.start_hour)
            assignments[key] = [
                self.employees[e].id
                for e in range(len(self.employees))
                if self.solver.Value(self.x[e][s])
            ]
        return assignments


# ---------------------------------------------------------------------------
# SimPy discrete-event simulation — stress test before deployment
# ---------------------------------------------------------------------------

def simulate_schedule(assignments: dict, shifts: list[ShiftConfig],
                      demand_variability: float = 0.15,
                      n_replications: int = 500) -> dict:
    """
    Monte Carlo DES: vary demand by ±variability across replications,
    measure coverage shortfall distribution.
    """
    shortfalls = []

    for _ in range(n_replications):
        env = simpy.Environment()
        total_shortfall = 0

        def location_process(env, shift):
            nonlocal total_shortfall
            key = shift.location_id + str(shift.start_hour)
            staff_on_hand = len(assignments.get(key, []))
            actual_demand = int(
                shift.min_staff * np.random.normal(1.0, demand_variability)
            )
            shortfall = max(0, actual_demand - staff_on_hand)
            total_shortfall += shortfall
            yield env.timeout(shift.duration_hours)

        for shift in shifts:
            env.process(location_process(env, shift))
        env.run()
        shortfalls.append(total_shortfall)

    arr = np.array(shortfalls)
    return {
        "mean_shortfall": float(arr.mean()),
        "p95_shortfall": float(np.percentile(arr, 95)),
        "p99_shortfall": float(np.percentile(arr, 99)),
        "zero_shortfall_pct": float((arr == 0).mean() * 100),
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(employees: list[Employee], shifts: list[ShiftConfig],
                 locations: list[Location]) -> dict:
    print("Step 1/3 — Genetic algorithm warm-start...")
    ga = GeneticScheduler(employees, shifts)
    warm_start = ga.run()

    print("Step 2/3 — CP-SAT optimization...")
    cp = CPSATScheduler(employees, shifts, warm_start=warm_start)
    assignments = cp.solve()

    print("Step 3/3 — SimPy simulation validation...")
    sim_results = simulate_schedule(assignments, shifts)

    return {
        "assignments": assignments,
        "simulation": sim_results,
        "coverage_rate": sim_results["zero_shortfall_pct"],
    }


# ---------------------------------------------------------------------------
# FastAPI what-if interface
# ---------------------------------------------------------------------------

app = FastAPI()

class WhatIfRequest(BaseModel):
    headcount_delta: int = 0
    demand_shock_pct: float = 0.0
    policy_change: Optional[str] = None

@app.post("/what-if")
def what_if(req: WhatIfRequest):
    """Leadership what-if endpoint: demand shock, headcount cuts, policy changes."""
    return {"status": "scenario queued", "params": req.dict()}


if __name__ == "__main__":
    # Example execution
    employees = [
        Employee(id=f"E{i:03d}", skills=["RN", "Tech"][i % 2:i % 2 + 1],
                 preferred_shifts=[7, 15][i % 2:i % 2 + 1])
        for i in range(50)
    ]
    shifts = [
        ShiftConfig(location_id=f"LOC{l}", start_hour=h,
                    duration_hours=8, required_skills={"RN": 1, "Tech": 2},
                    min_staff=3, max_staff=8)
        for l in range(5) for h in [7, 15, 23]
    ]
    locations = [Location(id=f"LOC{i}", name=f"Clinic {i}",
                          min_coverage=3, peak_windows=[(9, 17)],
                          skill_requirements={"RN": 1, "Tech": 2})
                 for i in range(5)]

    results = run_pipeline(employees, shifts, locations)
    print(f"Coverage rate: {results['coverage_rate']:.1f}%")
    print(f"P95 shortfall: {results['simulation']['p95_shortfall']:.1f} staff-hours")
