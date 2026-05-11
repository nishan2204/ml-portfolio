import type { Project } from '@/lib/projects'

interface Props {
  project: Project
  children?: React.ReactNode
}

export default function ProjectSection({ project, children }: Props) {
  const isBuilt = !!children

  return (
    <section
      id={`project-${project.id}`}
      className="py-24 px-6 border-b border-white/[0.04] scroll-mt-16"
    >
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="flex items-baseline gap-4 mb-12">
          <span
            className="text-7xl font-bold select-none leading-none"
            style={{ color: 'rgba(255,255,255,0.03)' }}
          >
            {String(project.id).padStart(2, '0')}
          </span>
          <h2 className="text-xl md:text-2xl font-bold text-white tracking-tight">{project.title}</h2>
        </div>

        {/* 2-col grid */}
        <div className="grid lg:grid-cols-2 gap-12 xl:gap-20 items-start">
          {/* Left: metadata */}
          <div className="space-y-9">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-neutral-700 mb-3">
                The Problem
              </p>
              <p className="text-neutral-400 leading-relaxed text-[15px]">{project.problem}</p>
            </div>

            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-neutral-700 mb-3">
                Approach
              </p>
              <p className="text-neutral-400 leading-relaxed text-[15px]">{project.approach}</p>
            </div>

            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-neutral-700 mb-3">
                Tech Stack
              </p>
              <div className="flex flex-wrap gap-1.5">
                {project.techStack.map((t) => (
                  <span
                    key={t}
                    className="px-2 py-0.5 text-[11px] text-neutral-600 bg-white/[0.04] border border-white/[0.07] rounded font-mono"
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>

            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.2em] text-neutral-700 mb-3">
                Impact
              </p>
              <ul className="space-y-2.5">
                {project.impact.map((item, i) => (
                  <li key={i} className="flex items-start gap-2.5">
                    <span className="text-emerald-500 text-xs mt-0.5 shrink-0 font-bold">↑</span>
                    <span className="text-neutral-300 text-[15px]">{item}</span>
                  </li>
                ))}
              </ul>
            </div>

            <p className="text-[11px] text-neutral-800 italic">
              Validated in a regulated, multi-site production environment.
            </p>
          </div>

          {/* Right: demo panel (sticky on desktop) */}
          <div className="lg:sticky lg:top-24 lg:self-start">
            <div className="bg-[#0b0b0b] border border-white/[0.08] rounded-2xl overflow-hidden">
              {/* Terminal-style header bar */}
              <div className="flex items-center justify-between px-4 py-3 border-b border-white/[0.06] bg-white/[0.01]">
                <div className="flex items-center gap-2">
                  <div className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-white/[0.08]" />
                    <span className="w-2.5 h-2.5 rounded-full bg-white/[0.08]" />
                    <span className="w-2.5 h-2.5 rounded-full bg-white/[0.08]" />
                  </div>
                  <span className="text-[11px] text-neutral-700 font-mono ml-2">{project.demoLabel}</span>
                </div>
                {isBuilt ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 font-mono">
                    ● live
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.04] text-neutral-700 border border-white/[0.06] font-mono">
                    ○ soon
                  </span>
                )}
              </div>

              {/* Content */}
              <div className="p-5">
                {isBuilt ? (
                  children
                ) : (
                  <div className="h-52 flex flex-col items-center justify-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-white/[0.03] border border-white/[0.07] flex items-center justify-center">
                      <svg
                        className="w-4 h-4 text-neutral-800"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={1.5}
                          d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                        />
                      </svg>
                    </div>
                    <p className="text-[12px] text-neutral-700">Interactive demo coming soon</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
