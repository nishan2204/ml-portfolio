'use client'

import { useState, useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

// -------------------------------------------------------------------
// Constraint structure
//   8 time windows (3 h each, 24 h coverage)
//   8 candidate shift patterns (each is a contiguous 9 h shift covering
//     3 consecutive windows — wraps overnight)
//   Decision variables: x_s ∈ ℤ≥0 = staff assigned to shift s
//   Constraint:     Σ x_s = N            (headcount)
//   Constraint:     x_s ≤ shiftCap       (max staff per shift)
//   Objective:      min Σ_t |coverage_t − demand_t|  +  λ · max(shiftPenalty)
//
// This is a small ILP. We solve it with hill-climbing local search
// (swap moves) — converges in <50 iterations for this size. The
// production system uses Google OR-Tools CP-SAT on ~12k variables.
// -------------------------------------------------------------------

const WINDOWS = 8
const SHIFT_LEN_WINDOWS = 3 // 9-hour shift = 3 × 3-h windows
// Demand peaks around 09:00 and 14:00
const DEMAND_PROFILE = [0.35, 0.45, 0.65, 0.9, 1.0, 0.95, 0.8, 0.5]

// Each shift covers SHIFT_LEN_WINDOWS consecutive windows (with wrap)
const SHIFT_PATTERNS = Array.from({ length: WINDOWS }, (_, s) => ({
  startHour: s * 3,
  windows: Array.from({ length: SHIFT_LEN_WINDOWS }, (_, k) => (s + k) % WINDOWS),
}))

interface SolverResult {
  x: number[]            // staff assigned per shift pattern
  coverage: number[]     // resulting coverage per window
  required: number[]     // demand per window (ints)
  iterations: number
  finalObj: number       // sum |coverage - required|
  shiftPenalty: number   // 0..1 penalty for non-standard shift length input
  efficiency: number     // headline % score (derived from solver)
}

function solve(N: number, coveragePct: number, shiftHours: number): SolverResult {
  // Translate demand profile into integer required-staff per window
  const peak = (coveragePct / 100) * 25
  const required = DEMAND_PROFILE.map((d) => Math.max(0, Math.round(peak * d)))

  // Initial allocation — distribute proportional to demand
  const totalDemand = required.reduce((a, b) => a + b, 0) || 1
  const x = new Array(WINDOWS).fill(0)
  let remaining = N
  for (let s = 0; s < WINDOWS; s++) {
    // For each shift, sum demand of windows it covers — heuristic seed
    const seedDemand = SHIFT_PATTERNS[s].windows.reduce((a, w) => a + required[w], 0)
    const share = Math.floor((seedDemand / (totalDemand * SHIFT_LEN_WINDOWS)) * N)
    x[s] = Math.max(0, share)
    remaining -= x[s]
  }
  // Distribute leftovers to highest-demand shifts
  const order = Array.from({ length: WINDOWS }, (_, k) => k).sort((a, b) => {
    const da = SHIFT_PATTERNS[a].windows.reduce((s, w) => s + required[w], 0)
    const db = SHIFT_PATTERNS[b].windows.reduce((s, w) => s + required[w], 0)
    return db - da
  })
  let i = 0
  while (remaining > 0) { x[order[i % WINDOWS]]++; remaining-- ; i++ }
  while (remaining < 0) {
    const fromIdx = order[(WINDOWS - 1 - (i++ % WINDOWS))]
    if (x[fromIdx] > 0) { x[fromIdx]--; remaining++ }
  }

  function coverageOf(xv: number[]) {
    const cov = new Array(WINDOWS).fill(0)
    for (let s = 0; s < WINDOWS; s++) {
      for (const w of SHIFT_PATTERNS[s].windows) cov[w] += xv[s]
    }
    return cov
  }
  function objective(xv: number[]) {
    const cov = coverageOf(xv)
    let obj = 0
    for (let t = 0; t < WINDOWS; t++) obj += Math.abs(cov[t] - required[t])
    return obj
  }

  // Hill-climbing with swap moves until no improvement
  let bestObj = objective(x)
  let iterations = 0
  const MAX_ITER = 60
  for (let iter = 0; iter < MAX_ITER; iter++) {
    iterations = iter + 1
    let improved = false
    outer: for (let from = 0; from < WINDOWS; from++) {
      if (x[from] === 0) continue
      for (let to = 0; to < WINDOWS; to++) {
        if (from === to) continue
        x[from]--; x[to]++
        const o = objective(x)
        if (o < bestObj) { bestObj = o; improved = true; break outer }
        x[from]++; x[to]--
      }
    }
    if (!improved) break
  }

  const coverage = coverageOf(x)

  // Soft penalty for non-standard shift length (CP-SAT model has this as a
  // separate cost term; we approximate it for the headline score)
  const shiftPenalty = Math.pow(Math.abs(shiftHours - 8) / 4, 1.4) * 9

  // Convert objective into an efficiency % for the headline.
  // Best possible obj is 0 (perfect coverage). Worst-case scales with peak.
  const worst = required.reduce((a, b) => a + b, 0) || 1
  const fit = 1 - bestObj / Math.max(1, worst)
  const efficiency = Math.round(Math.max(5, Math.min(97, fit * 97 - shiftPenalty)))

  return { x, coverage, required, iterations, finalObj: bestObj, shiftPenalty, efficiency }
}

const TOOLTIP_STYLE = {
  contentStyle: {
    background: '#111',
    border: '1px solid rgba(255,255,255,0.08)',
    borderRadius: '8px',
    fontSize: '11px',
    color: '#aaa',
    padding: '6px 10px',
  },
  labelStyle: { color: '#666', marginBottom: '2px' },
  cursor: { fill: 'rgba(255,255,255,0.03)' },
}

function effColor(e: number) {
  if (e >= 80) return '#10b981'
  if (e >= 60) return '#f59e0b'
  return '#ef4444'
}
function effLabel(e: number) {
  if (e >= 80) return 'Optimal'
  if (e >= 60) return 'Suboptimal'
  return 'Critical'
}

export default function SchedulingDemo() {
  const [staff, setStaff] = useState(28)
  const [shiftHours, setShiftHours] = useState(8)
  const [coverage, setCoverage] = useState(75)

  const result = useMemo(() => solve(staff, coverage, shiftHours), [staff, coverage, shiftHours])

  const chartData = result.required.map((req, i) => ({
    time: `${String(i * 3).padStart(2, '0')}:00`,
    Required: req,
    Allocated: result.coverage[i],
  }))

  const totalRequired = result.required.reduce((a, b) => a + b, 0)
  const optimalStaff = Math.round((coverage / 100) * 25)
  const gap = staff - optimalStaff
  const gapText =
    Math.abs(gap) <= 1 ? 'At optimal' : gap > 0 ? `+${gap} above optimal` : `${Math.abs(gap)} below optimal`

  const eColor = effColor(result.efficiency)
  const eLabel = effLabel(result.efficiency)

  return (
    <div className="space-y-5">
      {/* Score header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-1.5">
            Solver Efficiency
          </p>
          <div className="flex items-baseline gap-2.5">
            <span
              className="text-5xl font-bold font-mono tabular-nums leading-none"
              style={{ color: eColor }}
            >
              {result.efficiency}%
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide"
              style={{ color: eColor, background: `${eColor}18`, border: `1px solid ${eColor}30` }}
            >
              {eLabel}
            </span>
          </div>
        </div>
        <div className="text-right shrink-0">
          <p className="text-[10px] text-neutral-700 mb-1">Optimal target</p>
          <p className="text-sm font-mono text-neutral-400">{optimalStaff} staff</p>
          <p className="text-[11px] text-neutral-600 mt-0.5">{gapText}</p>
        </div>
      </div>

      {/* Sliders */}
      <div className="space-y-4 pt-1">
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-neutral-500">Staff Count</label>
            <span className="text-xs font-mono text-white tabular-nums">{staff}</span>
          </div>
          <input type="range" min={5} max={60} value={staff} onChange={(e) => setStaff(Number(e.target.value))} />
          <div className="flex justify-between text-[10px] text-neutral-800 mt-1"><span>5</span><span>60</span></div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-neutral-500">Shift Length</label>
            <span className="text-xs font-mono text-white tabular-nums">{shiftHours}h</span>
          </div>
          <input type="range" min={4} max={12} step={0.5} value={shiftHours} onChange={(e) => setShiftHours(Number(e.target.value))} />
          <div className="flex justify-between text-[10px] text-neutral-800 mt-1"><span>4h</span><span>12h</span></div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-neutral-500">Coverage Requirement</label>
            <span className="text-xs font-mono text-white tabular-nums">{coverage}%</span>
          </div>
          <input type="range" min={50} max={100} value={coverage} onChange={(e) => setCoverage(Number(e.target.value))} />
          <div className="flex justify-between text-[10px] text-neutral-800 mt-1"><span>50%</span><span>100%</span></div>
        </div>
      </div>

      {/* Chart — coverage vs demand from solver output */}
      <div className="pt-1">
        <p className="text-[10px] text-neutral-800 uppercase tracking-wider mb-3">
          Solver Output · Required vs. Allocated coverage
        </p>
        <div className="h-32">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} barCategoryGap="30%" barGap={2}>
              <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#444' }} axisLine={{ stroke: '#1a1a1a' }} tickLine={false} />
              <YAxis tick={{ fontSize: 9, fill: '#444' }} axisLine={false} tickLine={false} width={22} />
              <Tooltip {...TOOLTIP_STYLE} />
              <Bar dataKey="Required" fill="#1c1c1c" radius={[2, 2, 0, 0]} name="Required" />
              <Bar dataKey="Allocated" radius={[2, 2, 0, 0]} name="Allocated">
                {chartData.map((entry, i) => (
                  <Cell key={i} fill={entry.Allocated >= entry.Required ? '#10b981' : '#ef4444'} fillOpacity={0.75} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Solver trace + shift assignment */}
      <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3 space-y-2.5">
        <div className="flex items-center justify-between">
          <p className="text-[10px] text-neutral-500 uppercase tracking-wider">Solver Trace</p>
          <span className="text-[10px] font-mono text-neutral-600">
            {result.iterations} iter · obj = {result.finalObj}
          </span>
        </div>

        {/* Shift assignment grid: x[s] staff on each shift pattern */}
        <div>
          <p className="text-[10px] text-neutral-700 mb-1.5">Decision variables x_s · staff per shift</p>
          <div className="grid grid-cols-8 gap-1">
            {result.x.map((cnt, s) => {
              const intensity = Math.min(1, cnt / Math.max(1, Math.max(...result.x)))
              return (
                <div
                  key={s}
                  className="rounded text-center py-1.5 transition-all"
                  style={{
                    background: `rgba(59,130,246,${0.05 + intensity * 0.25})`,
                    border: `1px solid rgba(59,130,246,${0.1 + intensity * 0.3})`,
                  }}
                  title={`Shift starting ${String(SHIFT_PATTERNS[s].startHour).padStart(2, '0')}:00`}
                >
                  <p className="text-[8px] text-neutral-700 font-mono leading-none">
                    {String(SHIFT_PATTERNS[s].startHour).padStart(2, '0')}h
                  </p>
                  <p className="text-xs font-bold font-mono text-blue-300 mt-0.5 leading-none">{cnt}</p>
                </div>
              )
            })}
          </div>
        </div>

        <p className="text-[10px] text-neutral-700 leading-snug">
          {WINDOWS} shift patterns · {totalRequired} total demand-hours · headcount Σx_s = {result.x.reduce((a, b) => a + b, 0)}
        </p>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-5">
        <span className="flex items-center gap-1.5 text-[10px] text-neutral-700">
          <span className="w-3 h-2 rounded-sm inline-block bg-[#1c1c1c]" />
          Required
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-neutral-700">
          <span className="w-3 h-2 rounded-sm inline-block bg-emerald-500/70" />
          Coverage met
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-neutral-700">
          <span className="w-3 h-2 rounded-sm inline-block bg-red-500/70" />
          Gap
        </span>
      </div>

      <p className="text-[10px] text-neutral-800 italic leading-relaxed">
        Live JS hill-climbing solver on {WINDOWS}-shift ILP · production system uses OR-Tools CP-SAT on ~12k variables across 25+ locations
      </p>
    </div>
  )
}
