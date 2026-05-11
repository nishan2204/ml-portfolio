'use client'

import { useState } from 'react'

type Severity = 'critical' | 'warning' | 'ok'

interface ColumnProfile {
  name: string
  type: string
  missing: number
  outliers: number
  cardinality: number | string
  skew: number | null
  issues: { sev: Severity; msg: string }[]
}

const COLUMNS: ColumnProfile[] = [
  {
    name: 'claim_amount',
    type: 'float64',
    missing: 0.2,
    outliers: 3.8,
    cardinality: 14200,
    skew: 4.1,
    issues: [
      { sev: 'warning',  msg: 'High right skew (4.1) — log-transform recommended' },
      { sev: 'warning',  msg: '3.8% outliers above 3σ — review billing anomalies' },
    ],
  },
  {
    name: 'payer_id',
    type: 'object',
    missing: 0.0,
    outliers: 0,
    cardinality: 47,
    skew: null,
    issues: [
      { sev: 'ok', msg: 'Clean — 47 distinct payers, no nulls' },
    ],
  },
  {
    name: 'diagnosis_code',
    type: 'object',
    missing: 8.3,
    outliers: 0,
    cardinality: 2841,
    skew: null,
    issues: [
      { sev: 'critical', msg: '8.3% missing — required field for denial prediction' },
      { sev: 'warning',  msg: 'High cardinality (2,841) — consider ICD chapter grouping' },
    ],
  },
  {
    name: 'patient_age',
    type: 'int64',
    missing: 1.1,
    outliers: 0.4,
    cardinality: 89,
    skew: -0.3,
    issues: [
      { sev: 'warning', msg: '1.1% missing — impute with cohort median' },
      { sev: 'warning', msg: '0.4% values outside 0–120 range — validate source' },
    ],
  },
  {
    name: 'service_date',
    type: 'datetime64',
    missing: 0.0,
    outliers: 0,
    cardinality: 548,
    skew: null,
    issues: [
      { sev: 'ok', msg: 'Clean — spans 2022-01 to 2024-12, no nulls' },
    ],
  },
  {
    name: 'provider_npi',
    type: 'object',
    missing: 0.5,
    outliers: 0,
    cardinality: 312,
    skew: null,
    issues: [
      { sev: 'warning', msg: '0.5% missing — cross-reference NPI registry' },
    ],
  },
]

const SEV_META = {
  critical: { color: '#ef4444', bg: '#ef444415', border: '#ef444430', label: 'Critical' },
  warning:  { color: '#f59e0b', bg: '#f59e0b15', border: '#f59e0b30', label: 'Warning'  },
  ok:       { color: '#10b981', bg: '#10b98115', border: '#10b98130', label: 'OK'        },
}

function overallSev(col: ColumnProfile): Severity {
  if (col.issues.some((i) => i.sev === 'critical')) return 'critical'
  if (col.issues.some((i) => i.sev === 'warning'))  return 'warning'
  return 'ok'
}

const SCORE_LABELS = [
  { label: 'Completeness',   score: 91 },
  { label: 'Consistency',    score: 83 },
  { label: 'Validity',       score: 88 },
  { label: 'Overall DQ',     score: 87 },
]

export default function EDAQualityDemo() {
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState<Severity | 'all'>('all')

  const displayed = COLUMNS.filter(
    (c) => filter === 'all' || overallSev(c) === filter,
  )

  const col = selected ? COLUMNS.find((c) => c.name === selected) ?? null : null

  const critCount = COLUMNS.filter((c) => overallSev(c) === 'critical').length
  const warnCount = COLUMNS.filter((c) => overallSev(c) === 'warning').length

  return (
    <div className="space-y-4">
      {/* Overall scores */}
      <div className="grid grid-cols-4 gap-1.5">
        {SCORE_LABELS.map((s) => (
          <div
            key={s.label}
            className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2 text-center"
          >
            <p
              className="text-base font-bold font-mono"
              style={{ color: s.score >= 90 ? '#10b981' : s.score >= 80 ? '#f59e0b' : '#ef4444' }}
            >
              {s.score}
            </p>
            <p className="text-[9px] text-neutral-600 mt-0.5 leading-tight">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Issue summary badges */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[10px] text-neutral-600">6 columns profiled ·</span>
        {critCount > 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{ color: '#ef4444', background: '#ef444415', border: '1px solid #ef444430' }}>
            {critCount} Critical
          </span>
        )}
        {warnCount > 0 && (
          <span className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
            style={{ color: '#f59e0b', background: '#f59e0b15', border: '1px solid #f59e0b30' }}>
            {warnCount} Warnings
          </span>
        )}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-1.5">
        {(['all', 'critical', 'warning', 'ok'] as const).map((f) => (
          <button
            key={f}
            onClick={() => { setFilter(f); setSelected(null) }}
            className="text-[10px] px-2.5 py-1 rounded-full border transition-all capitalize"
            style={{
              borderColor: filter === f
                ? (f === 'all' ? 'rgba(255,255,255,0.2)' : SEV_META[f]?.color + '50')
                : 'rgba(255,255,255,0.06)',
              color: filter === f
                ? (f === 'all' ? '#fff' : SEV_META[f]?.color)
                : '#555',
              background: filter === f
                ? (f === 'all' ? 'rgba(255,255,255,0.06)' : SEV_META[f]?.bg)
                : 'transparent',
            }}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Column list */}
      <div className="space-y-1.5">
        {displayed.map((c) => {
          const sev = overallSev(c)
          const s = SEV_META[sev]
          return (
            <button
              key={c.name}
              onClick={() => setSelected(selected === c.name ? null : c.name)}
              className="w-full text-left rounded-lg px-3 py-2 transition-all"
              style={{
                background: selected === c.name ? s.bg : 'rgba(255,255,255,0.01)',
                border: `1px solid ${selected === c.name ? s.border : 'rgba(255,255,255,0.04)'}`,
              }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-neutral-300">{c.name}</span>
                  <span className="text-[9px] text-neutral-700 font-mono">{c.type}</span>
                </div>
                <div className="flex items-center gap-3">
                  {c.missing > 0 && (
                    <span className="text-[10px] text-neutral-600 font-mono">{c.missing}% null</span>
                  )}
                  <span
                    className="text-[9px] px-1.5 py-0.5 rounded font-semibold uppercase"
                    style={{ color: s.color, background: s.bg }}
                  >
                    {s.label}
                  </span>
                </div>
              </div>

              {/* Expanded issues */}
              {selected === c.name && (
                <div className="mt-2 space-y-1 pt-2 border-t border-white/[0.04]">
                  {c.issues.map((iss, i) => {
                    const issMeta = SEV_META[iss.sev]
                    return (
                      <p
                        key={i}
                        className="text-[11px] flex gap-1.5"
                        style={{ color: issMeta.color }}
                      >
                        <span className="shrink-0">
                          {iss.sev === 'critical' ? '✕' : iss.sev === 'warning' ? '!' : '✓'}
                        </span>
                        <span className="text-neutral-500">{iss.msg}</span>
                      </p>
                    )
                  })}
                  <div className="flex gap-4 mt-1.5 text-[10px] text-neutral-700">
                    <span>Cardinality: {typeof c.cardinality === 'number' ? c.cardinality.toLocaleString() : c.cardinality}</span>
                    {c.skew !== null && <span>Skewness: {c.skew}</span>}
                    <span>Outliers: {c.outliers}%</span>
                  </div>
                </div>
              )}
            </button>
          )
        })}
      </div>

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic dataset profile · 6 columns · 48,000 row simulation
      </p>
    </div>
  )
}
