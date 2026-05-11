'use client'

import { useState } from 'react'

// ----------------------------------------------------------------
// Synthetic clinical guideline corpus (RAG knowledge base)
// In production, this would live in DynamoDB with vector embeddings.
// Here we use lightweight keyword scoring for a transparent demo.
// ----------------------------------------------------------------
interface Guideline {
  id: string
  title: string
  source: string
  keywords: string[]
  body: string
}

const GUIDELINE_CORPUS: Guideline[] = [
  {
    id: 'fleischner-2017',
    title: 'Pulmonary Nodule Follow-up',
    source: 'Fleischner Society 2017',
    keywords: ['pulmonary nodule', 'lung nodule', 'lung lesion', 'pulmonary', 'lower lobe', 'upper lobe'],
    body: 'Solid pulmonary nodules <6 mm: no routine follow-up in low-risk patients. 6–8 mm: CT at 6–12 months. >8 mm: CT at 3 months, PET-CT, or tissue sampling depending on clinical risk.',
  },
  {
    id: 'acr-liver-2017',
    title: 'Incidental Hepatic Lesion',
    source: 'ACR White Paper 2017',
    keywords: ['hepatic', 'liver', 'hypodense', 'hepatic segment', 'liver lesion'],
    body: 'Indeterminate hepatic lesions <1 cm in low-risk patients: typically benign, no follow-up needed. 1–2 cm: MRI with contrast. >2 cm or high-risk patients: dedicated MRI within 3 months.',
  },
  {
    id: 'aua-renal-stone',
    title: 'Renal Calculus Management',
    source: 'AUA Guidelines',
    keywords: ['renal', 'kidney', 'calculus', 'nephrolithiasis', 'collecting system'],
    body: 'Asymptomatic non-obstructing renal calculi <5 mm: routine urologic correlation, hydration, follow-up imaging in 6–12 months. Obstructing or symptomatic stones require urgent urology consult.',
  },
  {
    id: 'iscd-vertebral',
    title: 'Vertebral Compression Deformity',
    source: 'ISCD/NOF Position Statement',
    keywords: ['compression', 'vertebral', 'compression fracture', 'vertebral body', 'spine', 'thoracic'],
    body: 'New or chronic-undetermined vertebral compression deformities warrant DXA bone density evaluation and assessment for osteoporosis. Acute findings or retropulsion require neurosurgical review.',
  },
  {
    id: 'acr-thyroid-tirads',
    title: 'Thyroid Incidentaloma (TI-RADS)',
    source: 'ACR TI-RADS 2017',
    keywords: ['thyroid', 'thyroid nodule'],
    body: 'Risk-stratify thyroid nodules by ACR TI-RADS score. TR4 nodules ≥1.5 cm or TR5 ≥1 cm warrant FNA biopsy. Smaller nodules: surveillance ultrasound.',
  },
  {
    id: 'acr-adrenal',
    title: 'Adrenal Incidentaloma',
    source: 'ACR Incidental Findings 2017',
    keywords: ['adrenal', 'adrenal mass', 'adrenal nodule'],
    body: 'Adrenal nodules <1 cm: no follow-up. 1–4 cm with benign imaging features: hormonal workup. >4 cm or suspicious features: surgical consult.',
  },
  {
    id: 'acr-pancreatic-cyst',
    title: 'Incidental Pancreatic Cyst',
    source: 'ACR/Fukuoka Consensus',
    keywords: ['pancreatic', 'pancreas', 'pancreatic cyst', 'ipmn'],
    body: 'Pancreatic cysts <2 cm without worrisome features: MRI/MRCP at 1 year, then every 2 years. Worrisome features (mural nodule, main duct dilation) warrant EUS and surgical referral.',
  },
  {
    id: 'sva-aneurysm',
    title: 'Aortic Aneurysm Surveillance',
    source: 'SVS / ACC Guidelines',
    keywords: ['aortic', 'aneurysm', 'aortic dilation', 'abdominal aortic'],
    body: 'AAA 3.0–3.9 cm: ultrasound every 2–3 years. 4.0–4.9 cm: every 12 months. ≥5.0 cm or rapidly expanding: vascular surgery consult.',
  },
]

// Lightweight keyword-overlap retrieval (TF-style)
// Production would use embeddings + cosine similarity in OpenSearch / Pinecone.
function retrieveGuidelines(text: string, topK = 3): (Guideline & { score: number })[] {
  const lower = text.toLowerCase()
  const scored = GUIDELINE_CORPUS.map((g) => ({
    ...g,
    score: g.keywords.reduce((acc, kw) => acc + (lower.includes(kw) ? 1 : 0), 0),
  }))
  return scored.filter((g) => g.score > 0).sort((a, b) => b.score - a.score).slice(0, topK)
}

const EXAMPLE_DOC = `RADIOLOGY REPORT
Patient ID: [REDACTED] | DOB: [REDACTED] | Date: March 14, 2025
Modality: CT Abdomen and Pelvis with contrast
Ordering Provider: Dr. [REDACTED]
Reason for Exam: Abdominal pain, rule out appendicitis

FINDINGS:

Appendix: Normal appendix visualized. No periappendiceal fat stranding or
fluid. Appendicitis excluded.

Liver: 1.3 cm hypodense lesion identified in hepatic segment VI, too small
to reliably characterize on this study. No prior imaging available for
comparison.

Kidneys: 4 mm non-obstructing calculus in the left renal collecting system.
Bilateral kidneys otherwise unremarkable.

Lung bases: 9 mm pulmonary nodule in the right lower lobe. Partially
visualized on this study. Clinical history and smoking status not provided.

Spine: Mild compression deformity at T11 vertebral body. Chronicity
unclear without prior imaging. No retropulsion.

Bowel/Mesentery: No obstruction. No free air or free fluid.

IMPRESSION:
1. No acute appendicitis.
2. Indeterminate hepatic lesion, segment VI — follow-up MRI liver recommended.
3. Right lower lobe pulmonary nodule — dedicated CT chest recommended per
   Fleischner Society guidelines.
4. Left renal calculus, non-obstructing — urologic correlation advised.
5. T11 vertebral compression deformity — bone density evaluation recommended.

Interpreting Radiologist: Dr. [REDACTED]
Report Status: Signed`

const SYSTEM_PROMPT = `You are a clinical findings triage agent. You are given (1) a radiology or clinical report and (2) retrieved clinical guidelines relevant to the report. Extract incidental findings that require follow-up, and ground each recommendation in the retrieved guidelines by referencing the guideline id.

Return ONLY valid JSON — no markdown, no explanation, no code fences:
{
  "findings": [
    {
      "description": "concise clinical finding (max 15 words)",
      "urgency": "ROUTINE" or "SOON" or "URGENT",
      "timeframe": "specific recommended timeframe e.g. 3 months / 30 days / 1 week",
      "action": "specific recommended follow-up action (max 20 words)",
      "citation": "guideline id you grounded this recommendation in (e.g. fleischner-2017), or 'none' if no guideline applied"
    }
  ],
  "summary": "one sentence summary of overall incidental finding burden"
}

Urgency: URGENT = follow-up within 7 days, SOON = within 30 days, ROUTINE = beyond 30 days.
Only include incidental findings that require follow-up. Do not include the primary reason for the study or normal findings.`

interface Finding {
  description: string
  urgency: 'ROUTINE' | 'SOON' | 'URGENT'
  timeframe: string
  action: string
  citation: string
}

interface AgentResult {
  findings: Finding[]
  summary: string
}

const URGENCY_STYLE = {
  URGENT:  { color: '#ef4444', bg: '#ef444418', border: '#ef444430', label: 'Urgent'  },
  SOON:    { color: '#f59e0b', bg: '#f59e0b18', border: '#f59e0b30', label: 'Soon'    },
  ROUTINE: { color: '#3b82f6', bg: '#3b82f618', border: '#3b82f630', label: 'Routine' },
}

type Phase = 'idle' | 'retrieving' | 'generating' | 'done'

export default function FindingsAgentDemo() {
  const [doc, setDoc] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [retrieved, setRetrieved] = useState<(Guideline & { score: number })[]>([])
  const [result, setResult] = useState<AgentResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function analyze() {
    if (!doc.trim()) return
    setResult(null)
    setError(null)
    setRetrieved([])

    // Step 1: retrieval (visible)
    setPhase('retrieving')
    await new Promise((r) => setTimeout(r, 500))
    const hits = retrieveGuidelines(doc, 4)
    setRetrieved(hits)
    await new Promise((r) => setTimeout(r, 350))

    // Step 2: generation with retrieved context
    setPhase('generating')

    try {
      const contextBlock = hits.length
        ? hits
            .map((g) => `[${g.id}] ${g.title} (${g.source})\n${g.body}`)
            .join('\n\n')
        : '(no relevant guidelines retrieved)'

      const userContent = `RETRIEVED CLINICAL GUIDELINES:\n${contextBlock}\n\n---\n\nREPORT:\n${doc}`

      const res = await fetch('/api/claude', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          model: 'claude-haiku-4-5-20251001',
          max_tokens: 1200,
          system: SYSTEM_PROMPT,
          messages: [{ role: 'user', content: userContent }],
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error ?? 'Request failed')

      const text = data.content?.[0]?.text ?? ''
      const cleaned = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```\s*$/, '').trim()
      const parsed: AgentResult = JSON.parse(cleaned)
      setResult(parsed)
      setPhase('done')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong')
      setPhase('idle')
    }
  }

  const loading = phase === 'retrieving' || phase === 'generating'

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <p className="text-[10px] text-neutral-700 uppercase tracking-widest">Document Input</p>
        <button
          onClick={() => { setDoc(EXAMPLE_DOC); setResult(null); setRetrieved([]); setError(null); setPhase('idle') }}
          className="text-[11px] text-blue-400 hover:text-blue-300 transition-colors"
        >
          Load example →
        </button>
      </div>

      <textarea
        value={doc}
        onChange={(e) => setDoc(e.target.value)}
        placeholder="Paste a radiology or clinical report, or click 'Load example' above..."
        rows={6}
        className="w-full bg-black/40 border border-white/[0.08] rounded-lg px-3 py-2.5 text-xs text-neutral-300 placeholder-neutral-700 resize-none focus:outline-none focus:border-white/20 transition-colors font-mono leading-relaxed"
      />

      <button
        onClick={analyze}
        disabled={loading || !doc.trim()}
        className="w-full py-2 text-xs font-semibold rounded-lg transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        style={{
          background: loading || !doc.trim() ? 'rgba(255,255,255,0.04)' : 'rgba(59,130,246,0.15)',
          border: '1px solid rgba(59,130,246,0.3)',
          color: loading || !doc.trim() ? '#555' : '#60a5fa',
        }}
      >
        {phase === 'retrieving' && (
          <>
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Retrieving guidelines from corpus...
          </>
        )}
        {phase === 'generating' && (
          <>
            <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Grounding recommendations in retrieved context...
          </>
        )}
        {phase !== 'retrieving' && phase !== 'generating' && 'Run RAG Pipeline'}
      </button>

      {error && (
        <div className="text-[11px] text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      {/* Retrieved guidelines (visible RAG step) */}
      {retrieved.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] text-neutral-700 uppercase tracking-widest">
            Step 1 · Retrieved {retrieved.length} of {GUIDELINE_CORPUS.length} guidelines
          </p>
          <div className="space-y-1.5">
            {retrieved.map((g) => (
              <div
                key={g.id}
                className="bg-blue-500/[0.04] border border-blue-500/15 rounded-lg p-2.5 transition-all duration-300"
              >
                <div className="flex items-center justify-between gap-2 mb-1">
                  <p className="text-[11px] text-blue-300 font-medium">{g.title}</p>
                  <span className="text-[9px] text-blue-400/60 font-mono shrink-0">
                    {g.id} · score {g.score}
                  </span>
                </div>
                <p className="text-[10px] text-neutral-600">{g.source}</p>
                <p className="text-[11px] text-neutral-500 leading-snug mt-1">{g.body}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Findings with citations */}
      {result && (
        <div className="space-y-3">
          <p className="text-[10px] text-neutral-700 uppercase tracking-widest">
            Step 2 · {result.findings.length} Finding{result.findings.length !== 1 ? 's' : ''} (grounded)
          </p>

          <div className="space-y-2">
            {result.findings.map((f, i) => {
              const s = URGENCY_STYLE[f.urgency] ?? URGENCY_STYLE.ROUTINE
              const cited = f.citation && f.citation !== 'none' ? f.citation : null
              return (
                <div
                  key={i}
                  className="rounded-lg p-3 space-y-1.5"
                  style={{ background: s.bg, border: `1px solid ${s.border}` }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs text-neutral-200 leading-snug">{f.description}</p>
                    <span
                      className="text-[10px] font-bold uppercase tracking-wider shrink-0 px-1.5 py-0.5 rounded"
                      style={{ color: s.color, background: s.bg }}
                    >
                      {s.label}
                    </span>
                  </div>
                  <p className="text-[11px] text-neutral-500">
                    <span className="text-neutral-600">Action:</span> {f.action}
                  </p>
                  <div className="flex items-center justify-between gap-2 pt-0.5">
                    <p className="text-[10px] text-neutral-700">Timeframe: {f.timeframe}</p>
                    {cited && (
                      <span
                        className="text-[9px] font-mono px-1.5 py-0.5 rounded"
                        style={{ color: '#60a5fa', background: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)' }}
                      >
                        cite: {cited}
                      </span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          <div className="bg-white/[0.02] border border-white/[0.06] rounded-lg p-3">
            <p className="text-[10px] text-neutral-700 uppercase tracking-wider mb-1">Agent Summary</p>
            <p className="text-xs text-neutral-400 leading-relaxed">{result.summary}</p>
          </div>

          <p className="text-[10px] text-neutral-800 italic">
            Powered by Claude · {GUIDELINE_CORPUS.length}-guideline synthetic corpus · keyword retrieval (production: vector search on Bedrock + DynamoDB)
          </p>
        </div>
      )}
    </div>
  )
}
