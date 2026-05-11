'use client'

import { useState } from 'react'

const METRICS = [
  { name: 'Monthly Revenue',       value: '$4.2M',  change: +12.3, unit: '%',  warn: false },
  { name: 'Patient Volume',        value: '18,400', change:  -3.1, unit: '%',  warn: true  },
  { name: 'Denial Rate',           value: '8.7%',   change:  -1.9, unit: 'pp', warn: false },
  { name: 'Days in AR',            value: '42',     change:  +5.2, unit: '%',  warn: true  },
  { name: 'Net Collection Rate',   value: '96.4%',  change:  +0.8, unit: 'pp', warn: false },
  { name: 'New Patient Acq.',      value: '1,240',  change: +22.1, unit: '%',  warn: false },
]

const ANOMALIES = [
  'Days in AR +5.2% despite revenue growth — possible billing-cycle lag',
  'Patient volume -3.1% while revenue +12.3% — revenue-per-visit improving',
]

const SYSTEM_PROMPT = `You are an executive insight analyst for a healthcare revenue cycle team. Given Q1 metrics and detected anomalies, write a concise executive narrative. Return ONLY valid JSON with no markdown fences:
{"headline":"one-sentence board-level summary","wins":["bullet 1","bullet 2","bullet 3"],"watchItems":["bullet 1","bullet 2"],"actions":["bullet 1","bullet 2","bullet 3"]}
Be specific and data-driven. Reference exact numbers from the input.`

interface Narrative {
  headline: string
  wins: string[]
  watchItems: string[]
  actions: string[]
}

export default function InsightNarrativeDemo() {
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<Narrative | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function generate() {
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const userContent = [
        'Period: Q1 2025',
        '',
        'Metrics:',
        ...METRICS.map((m) => `- ${m.name}: ${m.value} (${m.change > 0 ? '+' : ''}${m.change}${m.unit})`),
        '',
        'Detected anomalies:',
        ...ANOMALIES.map((a) => `- ${a}`),
      ].join('\n')

      const res = await fetch('/api/claude', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 1024,
          system: SYSTEM_PROMPT,
          messages: [{ role: 'user', content: userContent }],
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? 'Request failed')
      const text: string = data.content?.[0]?.text ?? ''
      const cleaned = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '').trim()
      setResult(JSON.parse(cleaned))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  function metricColor(m: typeof METRICS[0]) {
    if (m.warn) return m.change > 0 ? '#ef4444' : '#10b981'
    return m.change >= 0 ? '#10b981' : '#ef4444'
  }

  return (
    <div className="space-y-4">
      <p className="text-[10px] text-neutral-700 uppercase tracking-widest">
        Q1 2025 · Revenue Cycle Dashboard
      </p>

      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-1.5">
        {METRICS.map((m) => (
          <div
            key={m.name}
            className="bg-white/[0.02] border border-white/[0.06] rounded-md px-2.5 py-2"
          >
            <div className="flex items-center justify-between gap-1">
              <p className="text-[10px] text-neutral-600 leading-tight">{m.name}</p>
              <span
                className="text-[10px] font-mono shrink-0"
                style={{ color: metricColor(m) }}
              >
                {m.change > 0 ? '+' : ''}
                {m.change}
                {m.unit}
              </span>
            </div>
            <p className="text-sm font-bold font-mono text-white mt-0.5">{m.value}</p>
          </div>
        ))}
      </div>

      {/* Anomaly callouts */}
      <div className="space-y-1">
        {ANOMALIES.map((a, i) => (
          <div
            key={i}
            className="flex gap-2 text-[10px] text-neutral-500 bg-amber-500/[0.05] border border-amber-500/10 rounded px-2.5 py-1.5"
          >
            <span className="text-amber-500 shrink-0">!</span>
            {a}
          </div>
        ))}
      </div>

      <button
        onClick={generate}
        disabled={loading}
        className="w-full py-2 text-xs font-semibold rounded-lg transition-all duration-150 disabled:opacity-40 flex items-center justify-center gap-2"
        style={{
          background: loading ? 'rgba(255,255,255,0.04)' : 'rgba(59,130,246,0.15)',
          border: '1px solid rgba(59,130,246,0.3)',
          color: loading ? '#555' : '#60a5fa',
        }}
      >
        {loading ? (
          <>
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Generating executive narrative...
          </>
        ) : (
          'Generate Executive Narrative'
        )}
      </button>

      {error && (
        <div className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-3">
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
            <p className="text-[10px] text-blue-400 uppercase tracking-wider mb-1">Executive Summary</p>
            <p className="text-xs text-neutral-200 leading-relaxed">{result.headline}</p>
          </div>

          {[
            { key: 'wins',       title: 'Key Wins',             color: '#10b981', items: result.wins       },
            { key: 'watch',      title: 'Watch Items',          color: '#f59e0b', items: result.watchItems },
            { key: 'actions',    title: 'Recommended Actions',  color: '#3b82f6', items: result.actions    },
          ].map((s) => (
            <div
              key={s.key}
              className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3"
            >
              <p
                className="text-[10px] uppercase tracking-wider mb-2"
                style={{ color: s.color }}
              >
                {s.title}
              </p>
              <ul className="space-y-1.5">
                {s.items.map((item, i) => (
                  <li key={i} className="text-xs text-neutral-400 flex gap-2 leading-snug">
                    <span style={{ color: s.color }} className="shrink-0">
                      —
                    </span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <p className="text-[10px] text-neutral-800 italic">
            Powered by Claude · Synthetic Q1 data · no real records used
          </p>
        </div>
      )}
    </div>
  )
}
