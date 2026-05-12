export default function Hero() {
  return (
    <section id="hero" className="relative min-h-screen flex items-center justify-center px-6 overflow-hidden">
      {/* Subtle grid background */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
        }}
      />

      {/* Blue radial glow */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_90%_55%_at_50%_-10%,rgba(59,130,246,0.07),transparent)]" />

      <div className="relative max-w-4xl mx-auto text-center pt-16">
        {/* Status pill */}
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-white/[0.1] bg-white/[0.04] text-xs text-neutral-400 mb-10">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          Open to DS, ML Engineering &amp; AI leadership roles
        </div>

        {/* Name */}
        <p className="text-sm font-medium text-neutral-400 tracking-widest uppercase mb-4">Nishan Shetty</p>

        {/* Headline */}
        <h1 className="text-5xl sm:text-6xl md:text-[5rem] lg:text-[5.5rem] font-bold text-white mb-6 tracking-tight leading-[1.04]">
          From Raw Data to
          <br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 via-sky-300 to-emerald-400">
            Autonomous Action
          </span>
        </h1>

        {/* Bio */}
        <p className="text-base md:text-lg text-neutral-500 max-w-2xl mx-auto leading-relaxed mb-12">
          Data Scientist and AI Engineer with 8+ years building production ML systems that are accurate,
          explainable, and fast enough to matter. Proven in regulated, multi-site production
          environments, from scheduling optimization and revenue forecasting to multi-agent AI systems.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          <a
            href="#project-1"
            className="w-full sm:w-auto px-7 py-3 bg-white text-black text-sm font-semibold rounded-lg hover:bg-neutral-100 transition-colors duration-150"
          >
            View Projects
          </a>
          <a
            href="#contact"
            className="w-full sm:w-auto px-7 py-3 border border-white/[0.12] text-white text-sm font-medium rounded-lg hover:bg-white/[0.04] hover:border-white/20 transition-all duration-150"
          >
            Get in Touch →
          </a>
          <a
            href="/resume.pdf"
            target="_blank"
            rel="noopener noreferrer"
            className="w-full sm:w-auto px-7 py-3 border border-white/[0.12] text-neutral-400 text-sm font-medium rounded-lg hover:bg-white/[0.04] hover:text-white hover:border-white/20 transition-all duration-150 flex items-center justify-center gap-2"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
            </svg>
            Resume
          </a>
        </div>

        {/* Scroll chevron */}
        <div className="mt-24 flex justify-center">
          <svg
            className="w-4 h-4 text-neutral-700 animate-bounce"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>
    </section>
  )
}
