'use client'

import { useState } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from 'recharts'

const ASSETS = [
  { id: 'A1-HVAC-07', type: 'HVAC Unit',        health: 92, risk: 'low',    failEst: null          },
  { id: 'B3-PUMP-12', type: 'Hydraulic Pump',   health: 63, risk: 'medium', failEst: '14–21 days'  },
  { id: 'C2-COMP-03', type: 'Air Compressor',   health: 31, risk: 'high',   failEst: '4–6 days'    },
  { id: 'D5-CONV-09', type: 'Conveyor Belt',    health: 78, risk: 'low',    failEst: null          },
] as const

type AssetId = (typeof ASSETS)[number]['id']

// Deterministic sensor data using sin/cos (no Math.random — avoids hydration mismatch)
function buildSensorData(id: AssetId) {
  const BASE: Record<AssetId, { temp: number; vib: number }> = {
    'A1-HVAC-07': { temp: 67, vib: 3.1 },
    'B3-PUMP-12': { temp: 74, vib: 5.2 },
    'C2-COMP-03': { temp: 81, vib: 6.7 },
    'D5-CONV-09': { temp: 70, vib: 3.9 },
  }
  const b = BASE[id]
  const degrading = id === 'C2-COMP-03'

  return Array.from({ length: 24 }, (_, i) => {
    const spike = degrading && i >= 18 ? (i - 17) * 1.4 : 0
    const vibSpike = degrading && i >= 18 ? (i - 17) * 0.28 : 0
    return {
      time: `${String(i).padStart(2, '0')}:00`,
      temperature: +(b.temp + Math.sin(i * 0.9) * 3.5 + Math.cos(i * 0.4) * 1.5 + spike).toFixed(1),
      vibration:   +(b.vib  + Math.sin(i * 1.3) * 0.7 + Math.cos(i * 0.6) * 0.3 + vibSpike).toFixed(2),
      anomaly:     degrading && i >= 20 ? true : undefined,
    }
  })
}

const THRESHOLDS = { temperature: 85, vibration: 7.5 }
const RISK_META = {
  low:    { color: '#10b981', label: 'Healthy'  },
  medium: { color: '#f59e0b', label: 'Watch'    },
  high:   { color: '#ef4444', label: 'Critical' },
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

export default function IoTMaintenanceDemo() {
  const [selectedId, setSelectedId] = useState<AssetId>('C2-COMP-03')
  const [metric, setMetric] = useState<'temperature' | 'vibration'>('temperature')

  const asset   = ASSETS.find((a) => a.id === selectedId)!
  const data    = buildSensorData(selectedId)
  const risk    = RISK_META[asset.risk]
  const threshold = metric === 'temperature' ? THRESHOLDS.temperature : THRESHOLDS.vibration
  const unit    = metric === 'temperature' ? '°C' : 'g'

  return (
    <div className="space-y-4">
      {/* Health header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-1.5">
            Asset Health Score
          </p>
          <div className="flex items-baseline gap-2.5">
            <span
              className="text-5xl font-bold font-mono leading-none"
              style={{ color: risk.color }}
            >
              {asset.health}%
            </span>
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wide"
              style={{
                color: risk.color,
                background: risk.color + '18',
                border: `1px solid ${risk.color}30`,
              }}
            >
              {risk.label}
            </span>
          </div>
          <p className="text-[11px] text-neutral-600 mt-1">
            {asset.id} · {asset.type}
          </p>
        </div>
        {asset.failEst && (
          <div
            className="rounded-lg px-3 py-2 text-right shrink-0"
            style={{
              background: risk.color + '10',
              border: `1px solid ${risk.color}25`,
            }}
          >
            <p
              className="text-[10px] font-semibold uppercase tracking-wider"
              style={{ color: risk.color }}
            >
              Failure Predicted
            </p>
            <p className="text-xs text-neutral-400 mt-0.5">Est. {asset.failEst}</p>
          </div>
        )}
      </div>

      {/* Asset selector */}
      <div className="flex gap-1.5 flex-wrap">
        {ASSETS.map((a) => {
          const r = RISK_META[a.risk]
          return (
            <button
              key={a.id}
              onClick={() => setSelectedId(a.id)}
              className="text-[10px] px-2 py-1 rounded border transition-all font-mono"
              style={{
                borderColor: selectedId === a.id ? r.color + '55' : 'rgba(255,255,255,0.06)',
                color:       selectedId === a.id ? r.color : '#555',
                background:  selectedId === a.id ? r.color + '10' : 'transparent',
              }}
            >
              {a.id}
            </button>
          )
        })}
      </div>

      {/* Metric toggle */}
      <div className="flex rounded-lg overflow-hidden border border-white/[0.08] w-fit">
        {(['temperature', 'vibration'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMetric(m)}
            className={`px-3 py-1.5 text-[11px] font-mono uppercase tracking-wider transition-all ${
              metric === m ? 'bg-white/[0.08] text-white' : 'text-neutral-600 hover:text-neutral-400'
            }`}
          >
            {m === 'temperature' ? 'Temp' : 'Vibration'}
          </button>
        ))}
      </div>

      {/* Chart */}
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.03)"
              vertical={false}
            />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 8, fill: '#333' }}
              axisLine={false}
              tickLine={false}
              interval={5}
            />
            <YAxis tick={{ fontSize: 9, fill: '#444' }} axisLine={false} tickLine={false} width={28} />
            <Tooltip
              {...TOOLTIP_STYLE}
              formatter={(v: number) => [`${v}${unit}`, metric === 'temperature' ? 'Temp' : 'Vibration']}
            />
            <ReferenceLine
              y={threshold}
              stroke="#ef444440"
              strokeDasharray="4 3"
              label={{ value: 'Threshold', position: 'insideTopRight', fill: '#ef4444', fontSize: 8 }}
            />
            <Line
              type="monotone"
              dataKey={metric}
              stroke={risk.color}
              strokeWidth={1.5}
              dot={false}
              isAnimationActive
              animationDuration={500}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic IoT telemetry · 24 h window · 10,000+ asset fleet simulation
      </p>
    </div>
  )
}
