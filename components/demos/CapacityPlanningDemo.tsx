'use client'

import { useState } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from 'recharts'

interface SimResult {
  histogram: { bucket: string; count: number; pctile: string | null }[]
  p10: number
  p50: number
  p90: number
  breakeven: number
  summary: string
}

// Deterministic Monte Carlo using LCG seeded PRNG (avoids hydration mismatch)
function lcgRand(seed: number) {
  let s = seed
  return () => {
    s = (1664525 * s + 1013904223) & 0xffffffff
    return (s >>> 0) / 0xffffffff
  }
}

function runSimulation(demandGrowth: number, costIndex: number, headcount: number): SimResult {
  const rand = lcgRand(42 + demandGrowth * 7 + costIndex * 13 + headcount * 3)
  const N = 2000
  const results: number[] = []

  for (let i = 0; i < N; i++) {
    // Box-Muller with deterministic PRNG
    const u1 = Math.max(1e-9, rand())
    const u2 = rand()
    const z1 = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2)
    const z2 = Math.sqrt(-2 * Math.log(Math.max(1e-9, rand()))) * Math.cos(2 * Math.PI * rand())

    const demand  = demandGrowth / 100 + z1 * 0.08
    const cost    = costIndex    / 100 + z2 * 0.06
    const cap     = headcount / 50 + (rand() - 0.5) * 0.04

    const revenue = 10 + demand * 60
    const expenses = 5 + cost * 30 + (1 - cap) * 4
    results.push(Math.round((revenue - expenses) * 10) / 10)
  }

  results.sort((a, b) => a - b)

  const p10 = results[Math.floor(N * 0.1)]
  const p50 = results[Math.floor(N * 0.5)]
  const p90 = results[Math.floor(N * 0.9)]
  const min  = results[0]
  const max  = results[N - 1]
  const breakeven = Math.round((results.filter((r) => r < 0).length / N) * 100)

  const bucketCount = 12
  const bucketSize = (max - min) / bucketCount
  const histogram = Array.from({ length: bucketCount }, (_, i) => {
    const lo = min + i * bucketSize
    const hi = lo + bucketSize
    const count = results.filter((r) => r >= lo && r < hi).length
    const mid = (lo + hi) / 2
    let pctile: string | null = null
    if (Math.abs(mid - p10) < bucketSize) pctile = 'P10'
    if (Math.abs(mid - p50) < bucketSize) pctile = 'P50'
    if (Math.abs(mid - p90) < bucketSize) pctile = 'P90'
    return {
      bucket: `${lo.toFixed(0)}`,
      count,
      pctile,
    }
  })

  const direction = p50 > 0 ? 'positive' : 'negative'
  const summary = `Median outcome $${p50.toFixed(1)}M · ${breakeven}% probability of loss · P90 upside $${p90.toFixed(1)}M · P10 downside $${p10.toFixed(1)}M`

  return { histogram, p10, p50, p90, breakeven, summary }
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
  cursor: { fill: 'rgba(255,255,255,0.03)' },
}

export default function CapacityPlanningDemo() {
  const [demandGrowth, setDemandGrowth] = useState(15)
  const [costIndex,    setCostIndex]    = useState(20)
  const [headcount,    setHeadcount]    = useState(30)
  const [result, setResult] = useState<SimResult | null>(null)
  const [running, setRunning] = useState(false)

  function simulate() {
    setRunning(true)
    setTimeout(() => {
      setResult(runSimulation(demandGrowth, costIndex, headcount))
      setRunning(false)
    }, 600)
  }

  return (
    <div className="space-y-4">
      <p className="text-[10px] text-neutral-700 uppercase tracking-widest">
        Scenario Parameters
      </p>

      {/* Sliders */}
      <div className="space-y-3">
        {[
          { label: 'Demand Growth', value: demandGrowth, set: setDemandGrowth, min: 0,  max: 40, step: 1,  fmt: (v: number) => `+${v}% YoY` },
          { label: 'Cost Index',    value: costIndex,    set: setCostIndex,    min: 5,  max: 50, step: 1,  fmt: (v: number) => `${v}% of rev` },
          { label: 'Headcount Add', value: headcount,    set: setHeadcount,    min: 5,  max: 60, step: 5,  fmt: (v: number) => `${v} FTE` },
        ].map((s) => (
          <div key={s.label}>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-xs text-neutral-500">{s.label}</label>
              <span className="text-xs font-mono text-white">{s.fmt(s.value)}</span>
            </div>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={s.value}
              onChange={(e) => { s.set(Number(e.target.value)); setResult(null) }}
            />
          </div>
        ))}
      </div>

      <button
        onClick={simulate}
        disabled={running}
        className="w-full py-2 text-xs font-semibold rounded-lg transition-all duration-150 disabled:opacity-40 flex items-center justify-center gap-2"
        style={{
          background: running ? 'rgba(255,255,255,0.04)' : 'rgba(59,130,246,0.15)',
          border: '1px solid rgba(59,130,246,0.3)',
          color: running ? '#555' : '#60a5fa',
        }}
      >
        {running ? (
          <>
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Running 2,000 iterations...
          </>
        ) : (
          'Run Monte Carlo Simulation'
        )}
      </button>

      {result && (
        <div className="space-y-3">
          {/* Percentile stats */}
          <div className="grid grid-cols-3 gap-1.5">
            {[
              { label: 'P10 Downside', value: `$${result.p10.toFixed(1)}M`, color: '#ef4444' },
              { label: 'P50 Median',   value: `$${result.p50.toFixed(1)}M`, color: result.p50 >= 0 ? '#10b981' : '#ef4444' },
              { label: 'P90 Upside',   value: `$${result.p90.toFixed(1)}M`, color: '#10b981'  },
            ].map((s) => (
              <div
                key={s.label}
                className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2 text-center"
              >
                <p className="text-sm font-bold font-mono" style={{ color: s.color }}>
                  {s.value}
                </p>
                <p className="text-[9px] text-neutral-600 mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>

          {/* Histogram */}
          <div className="h-32">
            <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">
              Outcome Distribution (2,000 scenarios)
            </p>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={result.histogram} barCategoryGap="8%" margin={{ top: 4, right: 4, left: -14, bottom: 0 }}>
                <XAxis
                  dataKey="bucket"
                  tick={{ fontSize: 7, fill: '#333' }}
                  axisLine={false}
                  tickLine={false}
                  interval={2}
                />
                <YAxis tick={{ fontSize: 8, fill: '#333' }} axisLine={false} tickLine={false} width={24} />
                <Tooltip
                  {...TOOLTIP_STYLE}
                  formatter={(v: number) => [v, 'scenarios']}
                  labelFormatter={(l) => `~$${l}M`}
                />
                <ReferenceLine x={`${Math.round(0)}`} stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                  {result.histogram.map((d, i) => (
                    <Cell
                      key={i}
                      fill={Number(d.bucket) < 0 ? '#ef444460' : '#3b82f660'}
                      fillOpacity={d.pctile ? 1 : 0.6}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Summary */}
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
            <p className="text-[10px] text-neutral-600 uppercase tracking-wider mb-1">Scenario Summary</p>
            <p className="text-xs text-neutral-400 leading-relaxed">{result.summary}</p>
            {result.breakeven > 0 && (
              <p className="text-[11px] mt-1.5" style={{ color: result.breakeven > 20 ? '#ef4444' : '#f59e0b' }}>
                {result.breakeven}% probability of loss under this scenario
              </p>
            )}
          </div>
        </div>
      )}

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic Monte Carlo · 2,000 iterations · parametric model only
      </p>
    </div>
  )
}
