'use client'

import { useState } from 'react'
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

const CLUSTERS = [
  { id: 0, label: 'High-Value',  color: '#10b981', desc: 'High LTV, frequent referrers',  count: 312, roi: '+44%' },
  { id: 1, label: 'At-Risk',    color: '#ef4444', desc: 'Declining engagement, low tenure', count: 198, roi: '-12%' },
  { id: 2, label: 'Growth',     color: '#3b82f6', desc: 'Recent acqui, rising usage',       count: 441, roi: '+28%' },
  { id: 3, label: 'Dormant',    color: '#f59e0b', desc: 'Low activity, reactivation target', count: 267, roi: '+6%'  },
]

// Deterministic scatter points using trigonometric sequences (no Math.random)
function buildClusterPoints() {
  const centers = [
    [0.72, 0.78], [0.22, 0.28], [0.65, 0.32], [0.25, 0.68],
  ]
  const points: { x: number; y: number; cluster: number }[] = []
  const N = 28
  for (let c = 0; c < 4; c++) {
    for (let i = 0; i < N; i++) {
      const angle = (i / N) * 2 * Math.PI + c * 1.1
      const r = 0.08 + 0.06 * Math.abs(Math.sin(i * 0.7 + c))
      points.push({
        x: Math.min(0.97, Math.max(0.03, centers[c][0] + r * Math.cos(angle))),
        y: Math.min(0.97, Math.max(0.03, centers[c][1] + r * Math.sin(angle) * 0.85)),
        cluster: c,
      })
    }
  }
  return points
}

const ALL_POINTS = buildClusterPoints()

const NETWORK_STATS = [
  { label: 'Referral Volume',  value: '2.4k', delta: '+18%', up: true  },
  { label: 'Network Density',  value: '0.34', delta: '+0.07', up: true  },
  { label: 'High-Value Paths', value: '127',  delta: '+31%', up: true  },
  { label: 'Campaign ROI',     value: '25%',  delta: 'vs baseline', up: true },
]

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

export default function SegmentationDemo() {
  const [active, setActive] = useState<number | null>(null)

  const points = active === null ? ALL_POINTS : ALL_POINTS.filter((p) => p.cluster === active)

  return (
    <div className="space-y-4">
      {/* Scatter plot */}
      <div>
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">
          Patient Segments · PCA Projection (PC1 vs PC2)
        </p>
        <div className="h-40">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 4, right: 4, bottom: 10, left: -10 }}>
              <XAxis
                dataKey="x"
                type="number"
                domain={[0, 1]}
                tick={{ fontSize: 8, fill: '#333' }}
                axisLine={false}
                tickLine={false}
                label={{ value: 'PC1', position: 'insideBottom', fill: '#444', fontSize: 9, dy: 8 }}
              />
              <YAxis
                dataKey="y"
                type="number"
                domain={[0, 1]}
                tick={{ fontSize: 8, fill: '#333' }}
                axisLine={false}
                tickLine={false}
                width={20}
              />
              <Tooltip
                {...TOOLTIP_STYLE}
                content={({ payload }) => {
                  if (!payload?.length) return null
                  const d = payload[0]?.payload as { cluster: number }
                  const c = CLUSTERS[d.cluster]
                  return (
                    <div style={TOOLTIP_STYLE.contentStyle}>
                      <p style={{ color: c.color }}>{c.label}</p>
                      <p style={{ color: '#666', fontSize: 10, marginTop: 2 }}>{c.desc}</p>
                    </div>
                  )
                }}
              />
              <Scatter data={points} isAnimationActive animationDuration={400}>
                {points.map((p, i) => (
                  <Cell key={i} fill={CLUSTERS[p.cluster].color} fillOpacity={0.7} r={4} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Segment filter chips */}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => setActive(null)}
          className={`text-[10px] px-2.5 py-1 rounded-full border transition-all ${
            active === null
              ? 'bg-white/10 border-white/20 text-white'
              : 'border-white/[0.06] text-neutral-600 hover:text-neutral-400'
          }`}
        >
          All segments
        </button>
        {CLUSTERS.map((c) => (
          <button
            key={c.id}
            onClick={() => setActive(active === c.id ? null : c.id)}
            className="text-[10px] px-2.5 py-1 rounded-full border transition-all"
            style={{
              borderColor: active === c.id ? c.color + '55' : 'rgba(255,255,255,0.06)',
              color: active === c.id ? c.color : '#555',
              background: active === c.id ? c.color + '15' : 'transparent',
            }}
          >
            {c.label} · {active === c.id ? CLUSTERS[c.id].count : c.count}
          </button>
        ))}
      </div>

      {/* Active segment details */}
      {active !== null && (
        <div
          className="rounded-lg p-3 text-xs"
          style={{
            background: CLUSTERS[active].color + '10',
            border: `1px solid ${CLUSTERS[active].color}25`,
          }}
        >
          <p style={{ color: CLUSTERS[active].color }} className="font-semibold mb-0.5">
            {CLUSTERS[active].label} Segment
          </p>
          <p className="text-neutral-500">{CLUSTERS[active].desc}</p>
          <p className="text-neutral-600 mt-1">
            Campaign ROI uplift:{' '}
            <span style={{ color: CLUSTERS[active].color }} className="font-mono font-bold">
              {CLUSTERS[active].roi}
            </span>
          </p>
        </div>
      )}

      {/* Referral network stats */}
      <div>
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">Referral Network</p>
        <div className="grid grid-cols-4 gap-1.5">
          {NETWORK_STATS.map((s) => (
            <div
              key={s.label}
              className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2 text-center"
            >
              <p className="text-base font-bold font-mono text-blue-400">{s.value}</p>
              <p className="text-emerald-400 text-[9px] font-mono">{s.delta}</p>
              <p className="text-[9px] text-neutral-700 mt-0.5 leading-tight">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic PCA projection · 4-cluster K-Means · 1,218 patient cohort simulation
      </p>
    </div>
  )
}
