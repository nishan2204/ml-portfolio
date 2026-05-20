'use client'

import { useState, useMemo } from 'react'

// ---------------------------------------------------------------------------
// Synthetic access event generator + anomaly scorer
// ---------------------------------------------------------------------------

interface AccessEvent {
  id: string
  user: string
  role: string
  department: string
  patientId: string
  recordType: string
  timestamp: string
  hour: number
  accessCount: number        // records accessed in this session
  inCareRelationship: boolean
  daysSinceLastClinicalNote: number
  anomalyScore: number       // 0–1 (Isolation Forest approximation)
  lstmScore: number          // 0–1 (sequence deviation)
  graphFlag: boolean         // care relationship violation
  riskTier: 'low' | 'elevated' | 'high'
  reasons: string[]
}

const USERS = [
  { user: 'NRS-0142', role: 'RN',            dept: 'ICU'       },
  { user: 'PHY-0381', role: 'Physician',     dept: 'Cardiology'},
  { user: 'ADM-0027', role: 'Admin',         dept: 'Billing'   },
  { user: 'PHY-0219', role: 'Physician',     dept: 'Radiology' },
  { user: 'NRS-0098', role: 'RN',            dept: 'Oncology'  },
  { user: 'TEC-0055', role: 'Lab Tech',      dept: 'Lab'       },
  { user: 'ADM-0103', role: 'Admin',         dept: 'Records'   },
]

const RECORD_TYPES = ['Clinical Note', 'Lab Result', 'Imaging', 'Medication', 'Billing', 'Discharge Summary']

const BASELINE = {
  'RN':        { avgSessionRecords: 4,  stdRecords: 1.5, normalHours: [6,22],  careOverlapRate: 0.95 },
  'Physician': { avgSessionRecords: 6,  stdRecords: 2.0, normalHours: [7,21],  careOverlapRate: 0.98 },
  'Admin':     { avgSessionRecords: 12, stdRecords: 4.0, normalHours: [8,18],  careOverlapRate: 0.20 },
  'Lab Tech':  { avgSessionRecords: 8,  stdRecords: 2.5, normalHours: [6,20],  careOverlapRate: 0.85 },
}

function rng(seed: number) {
  let s = seed
  return () => { s = (s * 1664525 + 1013904223) & 0xffffffff; return (s >>> 0) / 0xffffffff }
}

function scoreEvent(event: Omit<AccessEvent, 'anomalyScore' | 'lstmScore' | 'riskTier' | 'reasons'>): AccessEvent {
  const baseline = BASELINE[event.role as keyof typeof BASELINE] || BASELINE['Admin']
  const reasons: string[] = []

  // Isolation Forest approximation: z-score on access volume + time deviation
  const volumeZ = (event.accessCount - baseline.avgSessionRecords) / Math.max(baseline.stdRecords, 1)
  const afterHours = event.hour < baseline.normalHours[0] || event.hour > baseline.normalHours[1]
  const careViolation = !event.inCareRelationship && baseline.careOverlapRate > 0.5
  const staleCare = event.daysSinceLastClinicalNote > 90

  let isoScore = Math.min(1, Math.max(0, (Math.abs(volumeZ) * 0.3 + (afterHours ? 0.25 : 0) +
    (careViolation ? 0.35 : 0) + (staleCare ? 0.15 : 0))))

  // LSTM sequence score: elevated if access pattern is unusual for this role/hour combo
  let lstmScore = Math.min(1, Math.max(0,
    (afterHours ? 0.3 : 0.05) +
    (volumeZ > 2 ? 0.3 : volumeZ > 1 ? 0.15 : 0) +
    (careViolation ? 0.25 : 0) +
    (Math.random() * 0.08)
  ))

  if (afterHours) reasons.push(`After-hours access (${event.hour}:00)`)
  if (volumeZ > 1.5) reasons.push(`${event.accessCount} records in session (${Math.round(volumeZ * 10) / 10}x baseline)`)
  if (careViolation) reasons.push('No documented care relationship')
  if (staleCare) reasons.push(`Last clinical note ${event.daysSinceLastClinicalNote}d ago`)

  const combinedScore = isoScore * 0.5 + lstmScore * 0.35 + (event.graphFlag ? 0.15 : 0)
  const riskTier: 'low' | 'elevated' | 'high' =
    combinedScore >= 0.55 ? 'high' : combinedScore >= 0.28 ? 'elevated' : 'low'

  return {
    ...event,
    anomalyScore: Math.round(isoScore * 100) / 100,
    lstmScore: Math.round(lstmScore * 100) / 100,
    riskTier,
    reasons,
  }
}

function generateEvents(seed: number, count: number = 18): AccessEvent[] {
  const rand = rng(seed)
  const events: AccessEvent[] = []
  const now = new Date('2025-03-14T14:30:00')

  // Inject 3 suspicious events
  const suspiciousIndices = new Set([2, 7, 13])

  for (let i = 0; i < count; i++) {
    const userIdx = Math.floor(rand() * USERS.length)
    const { user, role, dept } = USERS[userIdx]
    const baseline = BASELINE[role as keyof typeof BASELINE] || BASELINE['Admin']
    const isSuspicious = suspiciousIndices.has(i)

    const minutesAgo = Math.floor(rand() * 90)
    const ts = new Date(now.getTime() - minutesAgo * 60000)
    const hour = isSuspicious && rand() > 0.4
      ? Math.floor(rand() * 5)                  // late night
      : baseline.normalHours[0] + Math.floor(rand() * (baseline.normalHours[1] - baseline.normalHours[0]))

    const accessCount = isSuspicious
      ? Math.floor(baseline.avgSessionRecords * (2.5 + rand() * 2))
      : Math.max(1, Math.round(baseline.avgSessionRecords + (rand() - 0.5) * baseline.stdRecords * 2))

    const inCareRelationship = isSuspicious ? rand() < 0.25 : rand() < baseline.careOverlapRate
    const daysSinceNote = isSuspicious ? Math.floor(rand() * 200 + 60) : Math.floor(rand() * 30)
    const graphFlag = !inCareRelationship && baseline.careOverlapRate > 0.7

    const partial = {
      id: `EVT-${String(1000 + i).padStart(4, '0')}`,
      user,
      role,
      department: dept,
      patientId: `PT-${String(Math.floor(rand() * 9000) + 1000)}`,
      recordType: RECORD_TYPES[Math.floor(rand() * RECORD_TYPES.length)],
      timestamp: ts.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' }),
      hour,
      accessCount,
      inCareRelationship,
      daysSinceLastClinicalNote: daysSinceNote,
      graphFlag,
    }
    events.push(scoreEvent(partial))
  }

  return events.sort((a, b) => b.anomalyScore - a.anomalyScore)
}

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

const TIER_STYLE = {
  high:     { color: '#ef4444', bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.2)',   label: 'High'     },
  elevated: { color: '#f59e0b', bg: 'rgba(245,158,11,0.08)',  border: 'rgba(245,158,11,0.2)',  label: 'Elevated' },
  low:      { color: '#10b981', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.2)',  label: 'Low'      },
}

function ScoreBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1 bg-white/[0.05] rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all duration-500"
          style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="text-[10px] font-mono tabular-nums" style={{ color }}>
        {(value * 100).toFixed(0)}
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Demo component
// ---------------------------------------------------------------------------

export default function EHRAccessDemo() {
  const [seed, setSeed] = useState(42)
  const [selected, setSelected] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'high' | 'elevated' | 'low'>('all')

  const events = useMemo(() => generateEvents(seed), [seed])
  const filtered = filter === 'all' ? events : events.filter(e => e.riskTier === filter)

  const counts = {
    high: events.filter(e => e.riskTier === 'high').length,
    elevated: events.filter(e => e.riskTier === 'elevated').length,
    low: events.filter(e => e.riskTier === 'low').length,
  }

  const selectedEvent = events.find(e => e.id === selected)

  return (
    <div className="space-y-4">
      {/* Header stats */}
      <div className="grid grid-cols-3 gap-2">
        {(['high', 'elevated', 'low'] as const).map(tier => {
          const s = TIER_STYLE[tier]
          return (
            <button
              key={tier}
              onClick={() => setFilter(filter === tier ? 'all' : tier)}
              className="rounded-lg p-2.5 text-left transition-all"
              style={{
                background: filter === tier ? s.bg : 'rgba(255,255,255,0.02)',
                border: `1px solid ${filter === tier ? s.border : 'rgba(255,255,255,0.06)'}`,
              }}
            >
              <p className="text-[10px] uppercase tracking-wider mb-0.5" style={{ color: s.color }}>
                {s.label}
              </p>
              <p className="text-xl font-bold font-mono" style={{ color: s.color }}>
                {counts[tier]}
              </p>
            </button>
          )
        })}
      </div>

      {/* Simulate new batch button */}
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest">
          Access Log — Last 90 min · {filtered.length} events
        </p>
        <button
          onClick={() => { setSeed(s => s + 1); setSelected(null) }}
          className="text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
        >
          Simulate new batch →
        </button>
      </div>

      {/* Event list */}
      <div className="space-y-1.5 max-h-64 overflow-y-auto pr-0.5">
        {filtered.map(evt => {
          const s = TIER_STYLE[evt.riskTier]
          const isSelected = selected === evt.id
          return (
            <button
              key={evt.id}
              onClick={() => setSelected(isSelected ? null : evt.id)}
              className="w-full text-left rounded-lg px-3 py-2 transition-all"
              style={{
                background: isSelected ? s.bg : 'rgba(255,255,255,0.02)',
                border: `1px solid ${isSelected ? s.border : 'rgba(255,255,255,0.05)'}`,
              }}
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <span
                    className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded shrink-0"
                    style={{ color: s.color, background: s.bg }}
                  >
                    {s.label}
                  </span>
                  <span className="text-[11px] text-neutral-400 font-mono truncate">{evt.user}</span>
                  <span className="text-[10px] text-neutral-700 truncate hidden sm:block">
                    {evt.role} · {evt.department}
                  </span>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <span className="text-[10px] text-neutral-700 font-mono">{evt.timestamp}</span>
                  <span className="text-[10px] text-neutral-600">{evt.accessCount} records</span>
                  {evt.graphFlag && (
                    <span className="text-[9px] text-amber-500/80">⚠ graph</span>
                  )}
                </div>
              </div>
            </button>
          )
        })}
      </div>

      {/* Detail panel */}
      {selectedEvent && (() => {
        const s = TIER_STYLE[selectedEvent.riskTier]
        return (
          <div
            className="rounded-lg p-3.5 space-y-3 transition-all"
            style={{ background: s.bg, border: `1px solid ${s.border}` }}
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs font-semibold text-neutral-200">{selectedEvent.user}</p>
                <p className="text-[10px] text-neutral-500">
                  {selectedEvent.role} · {selectedEvent.department} · Patient {selectedEvent.patientId}
                </p>
              </div>
              <span
                className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded"
                style={{ color: s.color, background: `${s.color}18` }}
              >
                {s.label} Risk
              </span>
            </div>

            {/* Score breakdown */}
            <div className="space-y-1.5">
              <p className="text-[10px] text-neutral-700 uppercase tracking-wider">Model scores</p>
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-neutral-600 w-28 shrink-0">Isolation Forest</span>
                  <ScoreBar value={selectedEvent.anomalyScore} color={s.color} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-neutral-600 w-28 shrink-0">LSTM Sequence</span>
                  <ScoreBar value={selectedEvent.lstmScore} color={s.color} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-neutral-600 w-28 shrink-0">Graph Violation</span>
                  <div className="flex-1 h-1 bg-white/[0.05] rounded-full overflow-hidden">
                    <div className="h-full rounded-full"
                      style={{ width: selectedEvent.graphFlag ? '100%' : '0%', background: s.color }} />
                  </div>
                  <span className="text-[10px] font-mono" style={{ color: s.color }}>
                    {selectedEvent.graphFlag ? 'Yes' : 'No'}
                  </span>
                </div>
              </div>
            </div>

            {/* Feature attribution */}
            {selectedEvent.reasons.length > 0 && (
              <div className="space-y-1">
                <p className="text-[10px] text-neutral-700 uppercase tracking-wider">Risk factors</p>
                {selectedEvent.reasons.map((r, i) => (
                  <p key={i} className="text-[11px] text-neutral-400 flex items-start gap-1.5">
                    <span style={{ color: s.color }}>›</span> {r}
                  </p>
                ))}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2 pt-0.5">
              <div>
                <p className="text-[9px] text-neutral-700 mb-0.5">Record type</p>
                <p className="text-[11px] text-neutral-400">{selectedEvent.recordType}</p>
              </div>
              <div>
                <p className="text-[9px] text-neutral-700 mb-0.5">Care relationship</p>
                <p className="text-[11px]" style={{ color: selectedEvent.inCareRelationship ? '#10b981' : '#ef4444' }}>
                  {selectedEvent.inCareRelationship ? 'Documented' : 'Not found'}
                </p>
              </div>
            </div>
          </div>
        )
      })()}

      <p className="text-[10px] text-neutral-800 italic leading-relaxed">
        Live JS simulation · Isolation Forest + LSTM autoencoder + graph care-relationship model ·
        production system scores 10k+ events/min via Kafka on AWS SageMaker
      </p>
    </div>
  )
}
