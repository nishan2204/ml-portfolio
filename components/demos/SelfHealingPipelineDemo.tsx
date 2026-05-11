'use client'

import { useState } from 'react'

type FailureType = 'schema' | 'upstream' | 'compute' | 'timeout'
type StageStatus = 'idle' | 'running' | 'failed' | 'healed' | 'ok'

const STAGES = ['Ingest', 'Validate', 'Transform', 'Load', 'Publish'] as const
type Stage = (typeof STAGES)[number]

interface Incident {
  type: FailureType
  failedAt: Stage
  rootCause: string
  action: string
  mtd: string
  autoFixed: boolean
}

const FAILURE_SCENARIOS: Record<FailureType, Incident> = {
  schema: {
    type: 'schema',
    failedAt: 'Validate',
    rootCause: 'Schema drift — upstream added column "payer_v2", breaking Avro contract',
    action: 'Auto-applied schema evolution rule · re-queued 847 records · downstream notified',
    mtd: '2 min 14 s',
    autoFixed: true,
  },
  upstream: {
    type: 'upstream',
    failedAt: 'Ingest',
    rootCause: 'Upstream API returned 503 — source system maintenance window exceeded SLA',
    action: 'Escalated to on-call · incident P2 created · retry scheduled T+15 min',
    mtd: '4 min 07 s',
    autoFixed: false,
  },
  compute: {
    type: 'compute',
    failedAt: 'Transform',
    rootCause: 'OOM on Spark executor — partition skew on patient_id column',
    action: 'Auto-restarted with adaptive skew handling · repartitioned by claim_date instead',
    mtd: '3 min 41 s',
    autoFixed: true,
  },
  timeout: {
    type: 'timeout',
    failedAt: 'Load',
    rootCause: 'Snowflake write timeout — warehouse suspended due to 2 h idle policy',
    action: 'Auto-resumed warehouse · retried write · completed in 38 s on second attempt',
    mtd: '1 min 58 s',
    autoFixed: true,
  },
}

const FAILURE_LABELS: Record<FailureType, string> = {
  schema:   'Schema Drift',
  upstream: 'Upstream Failure',
  compute:  'OOM / Compute',
  timeout:  'Timeout',
}

const STATUS_COLOR: Record<StageStatus, string> = {
  idle:    '#333',
  running: '#3b82f6',
  failed:  '#ef4444',
  healed:  '#10b981',
  ok:      '#10b981',
}

function buildStageStatuses(incident: Incident | null, healed: boolean): Record<Stage, StageStatus> {
  const result: Record<Stage, StageStatus> = {
    Ingest: 'idle', Validate: 'idle', Transform: 'idle', Load: 'idle', Publish: 'idle',
  }
  if (!incident) return result
  let passed = false
  for (const s of STAGES) {
    if (s === incident.failedAt) {
      result[s] = healed ? 'healed' : 'failed'
      passed = true
    } else if (!passed) {
      result[s] = 'ok'
    }
  }
  return result
}

export default function SelfHealingPipelineDemo() {
  const [activeType, setActiveType] = useState<FailureType | null>(null)
  const [phase, setPhase] = useState<'idle' | 'detecting' | 'detected' | 'healing' | 'done'>('idle')

  const incident = activeType ? FAILURE_SCENARIOS[activeType] : null
  const healed = phase === 'done'
  const statuses = buildStageStatuses(incident, healed)

  function trigger(type: FailureType) {
    setActiveType(type)
    setPhase('detecting')
    setTimeout(() => setPhase('detected'), 900)
    setTimeout(() => setPhase('healing'), 2000)
    setTimeout(() => setPhase('done'), 3400)
  }

  function reset() {
    setActiveType(null)
    setPhase('idle')
  }

  const PHASE_LABELS = {
    idle:      null,
    detecting: { text: 'Monitoring agent scanning DAG...', color: '#3b82f6' },
    detected:  { text: `Root cause identified — ${incident?.rootCause ?? ''}`, color: '#ef4444' },
    healing:   { text: incident?.autoFixed ? 'Auto-remediating...' : 'Escalating to on-call...', color: '#f59e0b' },
    done:      { text: incident?.autoFixed ? `Resolved · MTTD ${incident?.mtd}` : `Escalated · MTTD ${incident?.mtd}`, color: incident?.autoFixed ? '#10b981' : '#ef4444' },
  }
  const phaseInfo = PHASE_LABELS[phase]

  return (
    <div className="space-y-4">
      {/* Pipeline DAG */}
      <div>
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-3">
          Airflow DAG · Real-time Status
        </p>
        <div className="flex items-center gap-0">
          {STAGES.map((s, i) => {
            const st = statuses[s]
            const color = STATUS_COLOR[st]
            return (
              <div key={s} className="flex items-center flex-1 min-w-0">
                <div className="flex-1 flex flex-col items-center">
                  <div
                    className="w-full rounded py-2 px-1 text-center transition-all duration-500"
                    style={{
                      background: color + '15',
                      border: `1px solid ${color}40`,
                    }}
                  >
                    <p className="text-[9px] font-mono" style={{ color }}>
                      {s}
                    </p>
                    {st === 'running' && (
                      <div className="mt-1 flex justify-center">
                        <div className="w-1 h-1 rounded-full bg-blue-400 animate-pulse" />
                      </div>
                    )}
                    {(st === 'failed' || st === 'healed') && (
                      <p className="text-[8px] mt-0.5" style={{ color }}>
                        {st === 'failed' ? '✕ err' : '✓ fixed'}
                      </p>
                    )}
                  </div>
                </div>
                {i < STAGES.length - 1 && (
                  <div className="w-3 h-px shrink-0" style={{ background: color + '50' }} />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Phase status bar */}
      {phaseInfo && (
        <div
          className="rounded-lg px-3 py-2.5 text-xs transition-all duration-300"
          style={{
            background: phaseInfo.color + '10',
            border: `1px solid ${phaseInfo.color}25`,
            color: phaseInfo.color,
          }}
        >
          {phase === 'detecting' || phase === 'healing' ? (
            <span className="flex items-center gap-2">
              <svg className="w-3 h-3 animate-spin shrink-0" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
              </svg>
              {phaseInfo.text}
            </span>
          ) : (
            phaseInfo.text
          )}
        </div>
      )}

      {/* Resolution card */}
      {phase === 'done' && incident && (
        <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Agent Action</p>
            <span
              className="text-[10px] font-semibold px-2 py-0.5 rounded-full"
              style={{
                color: incident.autoFixed ? '#10b981' : '#f59e0b',
                background: incident.autoFixed ? '#10b98118' : '#f59e0b18',
                border: `1px solid ${incident.autoFixed ? '#10b98130' : '#f59e0b30'}`,
              }}
            >
              {incident.autoFixed ? 'Auto-remediated' : 'Escalated'}
            </span>
          </div>
          <p className="text-xs text-neutral-400 leading-relaxed">{incident.action}</p>
        </div>
      )}

      {/* Failure trigger buttons */}
      <div>
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest mb-2">
          Inject Failure
        </p>
        <div className="grid grid-cols-2 gap-1.5">
          {(Object.keys(FAILURE_SCENARIOS) as FailureType[]).map((type) => (
            <button
              key={type}
              onClick={() => (phase === 'idle' || phase === 'done') ? trigger(type) : undefined}
              disabled={phase !== 'idle' && phase !== 'done'}
              className="text-[11px] py-2 px-3 rounded-lg border transition-all disabled:opacity-40 disabled:cursor-not-allowed text-left"
              style={{
                borderColor: activeType === type && phase !== 'idle' ? '#ef444440' : 'rgba(255,255,255,0.06)',
                color: activeType === type && phase !== 'idle' ? '#ef4444' : '#666',
                background: activeType === type && phase !== 'idle' ? '#ef444410' : 'transparent',
              }}
            >
              {FAILURE_LABELS[type]}
            </button>
          ))}
        </div>
        {phase === 'done' && (
          <button
            onClick={reset}
            className="mt-2 w-full text-[11px] py-1.5 rounded-lg border border-white/[0.06] text-neutral-600 hover:text-neutral-400 transition-colors"
          >
            Reset pipeline
          </button>
        )}
      </div>

      <p className="text-[10px] text-neutral-800 italic">
        Synthetic Airflow DAG simulation · no real pipelines or data
      </p>
    </div>
  )
}
