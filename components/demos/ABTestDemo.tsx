'use client'

import { useState, useMemo } from 'react'

// Two-proportion z-test
function zTest(
  convA: number,
  nA: number,
  convB: number,
  nB: number,
): { z: number; pValue: number; significant: boolean; lift: number } {
  const pA = convA / 100
  const pB = convB / 100
  const pPool = (pA * nA + pB * nB) / (nA + nB)
  const se = Math.sqrt(pPool * (1 - pPool) * (1 / nA + 1 / nB))
  const z = se > 0 ? (pB - pA) / se : 0
  // Normal CDF approximation (Abramowitz & Stegun)
  const absZ = Math.abs(z)
  const t = 1 / (1 + 0.2316419 * absZ)
  const poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
  const pOneSided = (1 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * absZ * absZ) * poly
  const pValue = Math.min(1, 2 * pOneSided)
  const lift = pA > 0 ? ((pB - pA) / pA) * 100 : 0
  return { z, pValue, significant: pValue < 0.05, lift }
}

const SYSTEM_PROMPT = `You are an expert experimentation analyst. Given A/B test results, write a concise decision memo. Return ONLY valid JSON with no markdown fences:
{"recommendation":"Ship"|"Hold"|"Extend","confidence":"High"|"Medium"|"Low","rationale":"2-3 sentence explanation referencing the specific numbers","caveats":["caveat 1","caveat 2"]}
Be direct. Flag novelty effects, peeking bias, or practical vs statistical significance distinctions when relevant.`

interface Memo {
  recommendation: 'Ship' | 'Hold' | 'Extend'
  confidence: 'High' | 'Medium' | 'Low'
  rationale: string
  caveats: string[]
}

const REC_COLOR = { Ship: '#10b981', Hold: '#ef4444', Extend: '#f59e0b' }
const CONF_COLOR = { High: '#10b981', Medium: '#f59e0b', Low: '#ef4444' }

export default function ABTestDemo() {
  const [convA, setConvA] = useState(12)
  const [convB, setConvB] = useState(15)
  const [nA,    setNA]    = useState(3200)
  const [nB,    setNB]    = useState(3100)
  const [loading, setLoading] = useState(false)
  const [memo, setMemo] = useState<Memo | null>(null)
  const [error, setError] = useState<string | null>(null)

  const stats = useMemo(() => zTest(convA, nA, convB, nB), [convA, nA, convB, nB])

  async function interpret() {
    setLoading(true)
    setMemo(null)
    setError(null)
    try {
      const content = [
        `Experiment: Homepage CTA Button Redesign`,
        `Control (A): ${convA}% conversion, n=${nA.toLocaleString()}`,
        `Variant (B): ${convB}% conversion, n=${nB.toLocaleString()}`,
        `Lift: ${stats.lift.toFixed(1)}%`,
        `Z-score: ${stats.z.toFixed(3)}`,
        `p-value: ${stats.pValue.toFixed(4)}`,
        `Statistically significant at 95% confidence: ${stats.significant ? 'Yes' : 'No'}`,
        `Runtime: 14 days`,
      ].join('\n')

      const res = await fetch('/api/claude', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 800,
          system: SYSTEM_PROMPT,
          messages: [{ role: 'user', content }],
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? 'Request failed')
      const text: string = data.content?.[0]?.text ?? ''
      const cleaned = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '').trim()
      setMemo(JSON.parse(cleaned))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const liftColor = stats.lift > 0 ? '#10b981' : '#ef4444'

  return (
    <div className="space-y-4">
      <p className="text-[10px] text-neutral-700 uppercase tracking-widest">
        Experiment Parameters
      </p>

      {/* Sliders */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { label: 'Control Conv. Rate', value: convA, set: setConvA, min: 5,   max: 40,   step: 1,   fmt: (v: number) => `${v}%`,   key: 'cA' },
          { label: 'Variant Conv. Rate', value: convB, set: setConvB, min: 5,   max: 40,   step: 1,   fmt: (v: number) => `${v}%`,   key: 'cB' },
          { label: 'Control Sample (n)',  value: nA,    set: setNA,    min: 500, max: 10000, step: 100, fmt: (v: number) => v.toLocaleString(), key: 'nA' },
          { label: 'Variant Sample (n)',  value: nB,    set: setNB,    min: 500, max: 10000, step: 100, fmt: (v: number) => v.toLocaleString(), key: 'nB' },
        ].map((s) => (
          <div key={s.key}>
            <div className="flex items-center justify-between mb-1.5">
              <label className="text-[10px] text-neutral-500">{s.label}</label>
              <span className="text-[10px] font-mono text-white">{s.fmt(s.value)}</span>
            </div>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={s.value}
              onChange={(e) => s.set(Number(e.target.value))}
            />
          </div>
        ))}
      </div>

      {/* Live stats */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5 text-center">
          <p className="text-lg font-bold font-mono" style={{ color: liftColor }}>
            {stats.lift > 0 ? '+' : ''}{stats.lift.toFixed(1)}%
          </p>
          <p className="text-[10px] text-neutral-600 mt-0.5">Relative Lift</p>
        </div>
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5 text-center">
          <p className="text-lg font-bold font-mono text-neutral-300">
            {stats.pValue < 0.001 ? '<0.001' : stats.pValue.toFixed(3)}
          </p>
          <p className="text-[10px] text-neutral-600 mt-0.5">p-value</p>
        </div>
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5 text-center">
          <p
            className="text-sm font-bold font-mono"
            style={{ color: stats.significant ? '#10b981' : '#ef4444' }}
          >
            {stats.significant ? 'Sig.' : 'Not sig.'}
          </p>
          <p className="text-[10px] text-neutral-600 mt-0.5">at α = 0.05</p>
        </div>
      </div>

      <button
        onClick={interpret}
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
            Writing decision memo...
          </>
        ) : (
          'Interpret with Claude'
        )}
      </button>

      {error && (
        <div className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {memo && (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <div>
              <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Recommendation</p>
              <p
                className="text-2xl font-bold font-mono"
                style={{ color: REC_COLOR[memo.recommendation] }}
              >
                {memo.recommendation}
              </p>
            </div>
            <div className="ml-auto text-right">
              <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Confidence</p>
              <p
                className="text-sm font-bold font-mono"
                style={{ color: CONF_COLOR[memo.confidence] }}
              >
                {memo.confidence}
              </p>
            </div>
          </div>
          <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
            <p className="text-[10px] text-neutral-600 uppercase tracking-wider mb-1.5">Rationale</p>
            <p className="text-xs text-neutral-400 leading-relaxed">{memo.rationale}</p>
          </div>
          {memo.caveats.length > 0 && (
            <div className="bg-amber-500/[0.05] border border-amber-500/10 rounded-lg p-3">
              <p className="text-[10px] text-amber-500 uppercase tracking-wider mb-1.5">Caveats</p>
              <ul className="space-y-1">
                {memo.caveats.map((c, i) => (
                  <li key={i} className="text-[11px] text-neutral-500 flex gap-1.5">
                    <span className="text-amber-600 shrink-0">—</span>{c}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <p className="text-[10px] text-neutral-800 italic">
            Powered by Claude · Synthetic experiment · no real user data
          </p>
        </div>
      )}
    </div>
  )
}
