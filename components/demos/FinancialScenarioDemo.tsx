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

type Scenario = 'bear' | 'base' | 'bull'

const SCENARIO_META = {
  bear: { label: 'Bear',   color: '#ef4444', demandDelta: -12, costDelta: +8  },
  base: { label: 'Base',   color: '#3b82f6', demandDelta:  +5, costDelta:  0  },
  bull: { label: 'Bull',   color: '#10b981', demandDelta: +18, costDelta: -4  },
}

function buildForecastData(scenario: Scenario) {
  const s = SCENARIO_META[scenario]
  return Array.from({ length: 12 }, (_, i) => {
    const base = 4.2 + i * 0.15
    const demandEffect = (s.demandDelta / 100) * base * (1 + i * 0.04)
    const costEffect   = (s.costDelta  / 100) * base
    const value = +(base + demandEffect + costEffect + Math.sin(i * 0.9) * 0.08).toFixed(2)
    return { month: `M${i + 1}`, revenue: value }
  })
}

interface AgentOutput {
  agent: string
  output: string
}

interface ScenarioResult {
  agents: AgentOutput[]
  narrative: string
  riskScore: number
  keyDecision: string
}

const SYSTEM_PROMPT = `You are orchestrating a 3-agent financial scenario planning system. Given scenario parameters, simulate the outputs of three specialized agents and produce a synthesis. Return ONLY valid JSON with no markdown fences:
{
  "agents": [
    {"agent": "Forecasting Agent", "output": "2-sentence revenue and demand projection with specific numbers"},
    {"agent": "Risk Assessment Agent", "output": "2-sentence downside risk analysis with probability estimates"},
    {"agent": "Synthesis Agent", "output": "2-sentence strategic recommendation for leadership"}
  ],
  "narrative": "3-sentence executive paragraph synthesizing all three agents",
  "riskScore": <integer 1-10>,
  "keyDecision": "one specific decision leadership should make based on this scenario"
}
Use realistic but synthetic numbers. Be direct and specific.`

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

export default function FinancialScenarioDemo() {
  const [scenario, setScenario] = useState<Scenario>('base')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ScenarioResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [visibleAgents, setVisibleAgents] = useState(0)

  const data = buildForecastData(scenario)
  const meta = SCENARIO_META[scenario]

  async function run() {
    setLoading(true)
    setResult(null)
    setError(null)
    setVisibleAgents(0)

    try {
      const s = SCENARIO_META[scenario]
      const content = [
        `Scenario: ${s.label}`,
        `Demand shock: ${s.demandDelta > 0 ? '+' : ''}${s.demandDelta}% vs. baseline`,
        `Cost structure change: ${s.costDelta > 0 ? '+' : ''}${s.costDelta}% vs. baseline`,
        `Base monthly revenue: $4.2M`,
        `Planning horizon: 12 months`,
        `Industry: Healthcare Revenue Cycle`,
      ].join('\n')

      const res = await fetch('/api/claude', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 1200,
          system: SYSTEM_PROMPT,
          messages: [{ role: 'user', content }],
        }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error ?? 'Request failed')
      const text: string = d.content?.[0]?.text ?? ''
      const cleaned = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '').trim()
      const parsed: ScenarioResult = JSON.parse(cleaned)
      setResult(parsed)

      // Reveal agents one by one
      setTimeout(() => setVisibleAgents(1), 200)
      setTimeout(() => setVisibleAgents(2), 800)
      setTimeout(() => setVisibleAgents(3), 1400)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  const AGENT_COLORS = ['#3b82f6', '#f59e0b', '#10b981']

  return (
    <div className="space-y-4">
      {/* Scenario selector */}
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest">Scenario</p>
        <div className="flex rounded-lg overflow-hidden border border-white/[0.08]">
          {(['bear', 'base', 'bull'] as Scenario[]).map((s) => (
            <button
              key={s}
              onClick={() => { setScenario(s); setResult(null); setVisibleAgents(0) }}
              className="px-3 py-1.5 text-[11px] font-mono uppercase tracking-wider transition-all"
              style={{
                background: scenario === s ? SCENARIO_META[s].color + '20' : 'transparent',
                color: scenario === s ? SCENARIO_META[s].color : '#555',
                borderRight: s !== 'bull' ? '1px solid rgba(255,255,255,0.06)' : undefined,
              }}
            >
              {SCENARIO_META[s].label}
            </button>
          ))}
        </div>
      </div>

      {/* Scenario description */}
      <div
        className="rounded-lg px-3 py-2 text-xs"
        style={{ background: meta.color + '10', border: `1px solid ${meta.color}25`, color: meta.color }}
      >
        Demand {meta.demandDelta > 0 ? '+' : ''}{meta.demandDelta}% · Costs {meta.costDelta > 0 ? '+' : ''}{meta.costDelta}%
      </div>

      {/* Forecast chart */}
      <div className="h-32">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 4, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 9, fill: '#444' }} axisLine={false} tickLine={false} interval={2} />
            <YAxis
              tick={{ fontSize: 9, fill: '#444' }}
              axisLine={false}
              tickLine={false}
              width={34}
              tickFormatter={(v) => `$${v.toFixed(1)}M`}
              domain={['auto', 'auto']}
            />
            <Tooltip
              {...TOOLTIP_STYLE}
              formatter={(v: number) => [`$${v.toFixed(2)}M`, 'Revenue']}
            />
            <Line
              type="monotone"
              dataKey="revenue"
              stroke={meta.color}
              strokeWidth={2}
              dot={false}
              isAnimationActive
              animationDuration={600}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Run button */}
      <button
        onClick={run}
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
            Running 3-agent analysis...
          </>
        ) : (
          'Run Multi-Agent Scenario Analysis'
        )}
      </button>

      {error && (
        <div className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Agent outputs */}
      {result && (
        <div className="space-y-3">
          {result.agents.slice(0, visibleAgents).map((a, i) => (
            <div
              key={i}
              className="rounded-lg p-3 transition-all duration-500"
              style={{ background: AGENT_COLORS[i] + '10', border: `1px solid ${AGENT_COLORS[i]}25` }}
            >
              <p
                className="text-[10px] font-semibold uppercase tracking-wider mb-1.5"
                style={{ color: AGENT_COLORS[i] }}
              >
                {a.agent}
              </p>
              <p className="text-xs text-neutral-400 leading-relaxed">{a.output}</p>
            </div>
          ))}

          {visibleAgents >= 3 && (
            <>
              <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
                <p className="text-[10px] text-neutral-500 uppercase tracking-wider mb-1.5">
                  Synthesis · Leadership Narrative
                </p>
                <p className="text-xs text-neutral-300 leading-relaxed">{result.narrative}</p>
              </div>

              <div className="flex gap-2">
                <div
                  className="flex-1 rounded-lg p-2.5 text-center"
                  style={{
                    background: result.riskScore > 6 ? '#ef444415' : result.riskScore > 3 ? '#f59e0b15' : '#10b98115',
                    border: `1px solid ${result.riskScore > 6 ? '#ef444430' : result.riskScore > 3 ? '#f59e0b30' : '#10b98130'}`,
                  }}
                >
                  <p
                    className="text-xl font-bold font-mono"
                    style={{ color: result.riskScore > 6 ? '#ef4444' : result.riskScore > 3 ? '#f59e0b' : '#10b981' }}
                  >
                    {result.riskScore}/10
                  </p>
                  <p className="text-[10px] text-neutral-600">Risk Score</p>
                </div>
                <div className="flex-[3] bg-white/[0.02] border border-white/[0.06] rounded-lg p-2.5">
                  <p className="text-[10px] text-neutral-600 mb-1">Key Decision</p>
                  <p className="text-xs text-neutral-300 leading-snug">{result.keyDecision}</p>
                </div>
              </div>
            </>
          )}

          <p className="text-[10px] text-neutral-800 italic">
            Powered by Claude · Synthetic financial model · no real data
          </p>
        </div>
      )}
    </div>
  )
}
