'use client'

import { useState } from 'react'
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  CartesianGrid,
} from 'recharts'

type Model = 'arima' | 'lstm'

const MONTH_LABELS = [
  "Jan '24", "Feb '24", "Mar '24", "Apr '24", "May '24", "Jun '24",
  "Jul '24", "Aug '24", "Sep '24", "Oct '24", "Nov '24", "Dec '24",
  "Jan '25", "Feb '25", "Mar '25", "Apr '25", "May '25", "Jun '25",
  "Jul '25", "Aug '25", "Sep '25", "Oct '25", "Nov '25", "Dec '25",
]

// -------------------------------------------------------------------
// Synthetic data — 18 months actual + 6 months forecast
// Months 16–17 overlap (validation window) so both actual & predicted show.
// ARIMA: wider confidence bands, slightly less accurate.
// LSTM:  tighter bands, captures non-linear seasonal pattern better.
// -------------------------------------------------------------------
function buildData(model: Model) {
  return MONTH_LABELS.map((label, i) => {
    const trend = 1150 - i * 14
    const seasonal = Math.sin((i / 12) * 2 * Math.PI) * 90
    const noise = Math.sin(i * 4.7) * 45 + Math.cos(i * 2.3) * 35

    const actual = i < 18 ? Math.round(Math.max(300, trend + seasonal + noise)) : undefined

    let predicted: number | undefined
    let bandLower: number | undefined
    let bandHeight: number | undefined

    if (i >= 16) {
      const base = trend + seasonal
      const horizon = Math.max(0, i - 17) // months into pure forecast

      if (model === 'arima') {
        predicted = Math.round(base + Math.sin(i * 2.1) * 22)
        const bw = 65 + horizon * 14
        bandLower = Math.max(0, predicted - bw)
        bandHeight = bw * 2
      } else {
        predicted = Math.round(base + Math.sin(i * 2.1) * 11 + Math.cos(i * 1.8) * 13)
        const bw = 45 + horizon * 9
        bandLower = Math.max(0, predicted - bw)
        bandHeight = bw * 2
      }
    }

    return { month: label, actual, predicted, bandLower, bandHeight }
  })
}

const MODEL_META = {
  arima: { color: '#3b82f6', label: 'ARIMA + Seasonal Decomp', mae: '12.4%' },
  lstm:  { color: '#10b981', label: 'Bi-LSTM + Attention',     mae:  '8.7%' },
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
  cursor: { stroke: 'rgba(255,255,255,0.06)' },
}

export default function RevenueForecastDemo() {
  const [model, setModel] = useState<Model>('arima')
  const data = buildData(model)
  const meta = MODEL_META[model]

  return (
    <div className="space-y-5">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">Model</p>
          <div className="flex rounded-lg overflow-hidden border border-white/[0.08]">
            {(['arima', 'lstm'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setModel(m)}
                className={`px-4 py-1.5 text-xs font-mono uppercase tracking-wider transition-all duration-200 ${
                  model === m
                    ? 'bg-white/[0.08] text-white'
                    : 'text-neutral-600 hover:text-neutral-400'
                }`}
              >
                {m}
              </button>
            ))}
          </div>
          <p className="text-[10px] text-neutral-600 mt-1.5">{meta.label}</p>
        </div>

        <div className="text-right">
          <p className="text-[10px] text-neutral-700 mb-1">Forecast Error (MAE)</p>
          <p
            className="text-4xl font-bold font-mono tabular-nums transition-colors duration-300"
            style={{ color: meta.color }}
          >
            {meta.mae}
          </p>
        </div>
      </div>

      {/* Chart */}
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.03)"
              vertical={false}
            />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 9, fill: '#444' }}
              axisLine={false}
              tickLine={false}
              interval={5}
            />
            <YAxis
              tick={{ fontSize: 9, fill: '#444' }}
              axisLine={false}
              tickLine={false}
              width={32}
            />
            <Tooltip {...TOOLTIP_STYLE} />

            {/* Confidence band — stacked areas (proper recharts range pattern) */}
            <Area
              type="monotone"
              dataKey="bandLower"
              stackId="band"
              fill="transparent"
              stroke="none"
              isAnimationActive
              animationDuration={600}
            />
            <Area
              type="monotone"
              dataKey="bandHeight"
              stackId="band"
              fill={`${meta.color}18`}
              stroke="none"
              name="95% confidence"
              isAnimationActive
              animationDuration={600}
            />

            {/* Forecast-start reference line */}
            <ReferenceLine
              x="Jul '25"
              stroke="rgba(255,255,255,0.08)"
              strokeDasharray="4 3"
              label={{
                value: 'Forecast →',
                position: 'insideTopRight',
                fill: '#444',
                fontSize: 9,
                dy: -2,
              }}
            />

            {/* Actual */}
            <Line
              type="monotone"
              dataKey="actual"
              stroke="#d4d4d4"
              strokeWidth={1.5}
              dot={false}
              name="Actual"
              connectNulls={false}
              isAnimationActive
              animationDuration={800}
            />

            {/* Predicted */}
            <Line
              type="monotone"
              dataKey="predicted"
              stroke={meta.color}
              strokeWidth={1.5}
              strokeDasharray="5 4"
              dot={false}
              name="Predicted"
              connectNulls
              isAnimationActive
              animationDuration={600}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-5 flex-wrap">
        <span className="flex items-center gap-1.5 text-[10px] text-neutral-600">
          <span className="w-4 h-px bg-neutral-400 inline-block" />
          Actual denial volume
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-neutral-600">
          <span
            className="w-4 h-px inline-block"
            style={{ background: meta.color, borderTop: `1px dashed ${meta.color}` }}
          />
          Predicted
        </span>
        <span className="flex items-center gap-1.5 text-[10px] text-neutral-600">
          <span
            className="w-3 h-3 rounded-sm inline-block opacity-40"
            style={{ background: meta.color }}
          />
          95% Confidence Band
        </span>
      </div>

      {/* Impact stats */}
      <div className="grid grid-cols-3 gap-2 pt-1">
        {[
          { label: 'Reprocessing Cost', value: '77%', suffix: '↓' },
          { label: 'Denial Rate',       value: '25%', suffix: '↓' },
          { label: 'Forecast Error',    value: '18%', suffix: '↓' },
        ].map((s) => (
          <div
            key={s.label}
            className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5 text-center"
          >
            <p className="text-xl font-bold font-mono text-emerald-400">
              {s.value}
              <span className="text-sm ml-0.5">{s.suffix}</span>
            </p>
            <p className="text-[10px] text-neutral-600 mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic data · 24-month simulation · nightly retraining cadence
      </p>
    </div>
  )
}
