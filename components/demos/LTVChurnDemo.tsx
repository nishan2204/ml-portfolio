'use client'

import { useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'

const COHORTS = [
  { id: 'C1', label: 'Jan 2024 · Organic',    color: '#10b981', retention: [100, 84, 71, 62, 57, 53], ltv: [0, 420, 760, 1020, 1240, 1430] },
  { id: 'C2', label: 'Mar 2024 · Paid Search', color: '#3b82f6', retention: [100, 76, 58, 44, 37, 32], ltv: [0, 380, 640, 820,  940,  1010] },
  { id: 'C3', label: 'May 2024 · Referral',    color: '#a78bfa', retention: [100, 89, 79, 72, 68, 65], ltv: [0, 460, 840, 1140, 1390, 1600] },
  { id: 'C4', label: 'Aug 2024 · Direct Mail', color: '#f59e0b', retention: [100, 71, 52, 41, 35, 30], ltv: [0, 310, 520, 660,  750,  800]  },
  { id: 'C5', label: 'Nov 2024 · Partner',     color: '#ec4899', retention: [100, 82, 68, 58, 52, 48], ltv: [0, 400, 720, 970,  1170, 1330] },
]

const MONTHS = ['M0', 'M1', 'M2', 'M3', 'M4', 'M5']

function retentionColor(pct: number) {
  if (pct >= 80) return { bg: '#10b98120', text: '#10b981' }
  if (pct >= 60) return { bg: '#3b82f620', text: '#3b82f6'  }
  if (pct >= 40) return { bg: '#f59e0b20', text: '#f59e0b'  }
  return                 { bg: '#ef444420', text: '#ef4444'  }
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
  cursor: { stroke: 'rgba(255,255,255,0.05)' },
}

export default function LTVChurnDemo() {
  const [view, setView] = useState<'retention' | 'ltv'>('retention')
  const [highlighted, setHighlighted] = useState<string | null>(null)

  // Build line chart data
  const lineData = MONTHS.map((m, i) => {
    const row: Record<string, number | string> = { month: m }
    for (const c of COHORTS) {
      row[c.id] = view === 'retention' ? c.retention[i] : c.ltv[i]
    }
    return row
  })

  return (
    <div className="space-y-4">
      {/* View toggle */}
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest">Cohort Analysis</p>
        <div className="flex rounded-lg overflow-hidden border border-white/[0.08]">
          {(['retention', 'ltv'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`px-3 py-1.5 text-[11px] font-mono uppercase tracking-wider transition-all ${
                view === v ? 'bg-white/[0.08] text-white' : 'text-neutral-600 hover:text-neutral-400'
              }`}
            >
              {v === 'retention' ? 'Retention' : 'LTV'}
            </button>
          ))}
        </div>
      </div>

      {/* Retention heatmap (only for retention view) */}
      {view === 'retention' && (
        <div>
          <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">
            Retention Heatmap
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-[9px]">
              <thead>
                <tr>
                  <th className="text-left text-neutral-600 pb-1.5 pr-2 font-normal w-28">Cohort</th>
                  {MONTHS.map((m) => (
                    <th key={m} className="text-neutral-600 pb-1.5 px-1 font-mono font-normal text-center">
                      {m}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {COHORTS.map((c) => (
                  <tr
                    key={c.id}
                    className="cursor-pointer"
                    onMouseEnter={() => setHighlighted(c.id)}
                    onMouseLeave={() => setHighlighted(null)}
                  >
                    <td className="pr-2 py-0.5">
                      <span
                        className="text-[9px] font-mono"
                        style={{ color: highlighted === c.id ? c.color : '#555' }}
                      >
                        {c.id}
                      </span>
                    </td>
                    {c.retention.map((r, i) => {
                      const s = retentionColor(r)
                      return (
                        <td key={i} className="px-0.5 py-0.5">
                          <div
                            className="rounded text-center py-1 px-1 font-mono font-bold transition-all"
                            style={{
                              background: s.bg,
                              color: s.text,
                              outline: highlighted === c.id ? `1px solid ${c.color}50` : 'none',
                            }}
                          >
                            {r}%
                          </div>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* LTV / line chart */}
      <div>
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">
          {view === 'retention' ? '6-Month LTV Trajectory ($)' : 'Cumulative LTV per Patient ($)'}
        </p>
        <div className="h-36">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={lineData} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 9, fill: '#444' }} axisLine={false} tickLine={false} />
              <YAxis
                tick={{ fontSize: 9, fill: '#444' }}
                axisLine={false}
                tickLine={false}
                width={32}
                tickFormatter={(v) => view === 'ltv' ? `$${(v / 1000).toFixed(0)}k` : `${v}%`}
              />
              <Tooltip
                {...TOOLTIP_STYLE}
                formatter={(v: number, name: string) => [
                  view === 'ltv' ? `$${v.toLocaleString()}` : `${v}%`,
                  COHORTS.find((c) => c.id === name)?.label ?? name,
                ]}
              />
              {COHORTS.map((c) => (
                <Line
                  key={c.id}
                  type="monotone"
                  dataKey={c.id}
                  stroke={c.color}
                  strokeWidth={highlighted === c.id ? 2 : 1}
                  strokeOpacity={highlighted && highlighted !== c.id ? 0.2 : 0.85}
                  dot={false}
                  isAnimationActive
                  animationDuration={500}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Cohort legend */}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {COHORTS.map((c) => (
          <span
            key={c.id}
            className="flex items-center gap-1.5 text-[10px] cursor-pointer transition-colors"
            style={{ color: highlighted === c.id ? c.color : '#555' }}
            onMouseEnter={() => setHighlighted(c.id)}
            onMouseLeave={() => setHighlighted(null)}
          >
            <span className="w-3 h-px inline-block" style={{ background: c.color }} />
            {c.label}
          </span>
        ))}
      </div>

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic cohort data · 5 acquisition channels · 6-month window
      </p>
    </div>
  )
}
