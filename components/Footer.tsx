export default function Footer() {
  return (
    <footer id="contact" className="border-t border-white/[0.06] pt-20 pb-10 px-6">
      <div className="max-w-7xl mx-auto">
        <div className="grid md:grid-cols-2 gap-12 items-start mb-16">
          {/* Left */}
          <div>
            <h2 className="text-3xl md:text-4xl font-bold text-white mb-4 tracking-tight">
              Let's work together
            </h2>
            <p className="text-neutral-500 leading-relaxed mb-6 max-w-md">
              Open to senior Data Science, ML Engineering, and AI leadership roles. I build systems
              that make it to production and stay there.
            </p>
            {/* Replace with your email */}
            <a
              href="mailto:nishan2204@gmail.com"
              className="inline-flex items-center gap-2 text-blue-400 hover:text-blue-300 transition-colors text-sm group"
            >
              nishan2204@gmail.com
              <svg
                className="w-3.5 h-3.5 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
            </a>
          </div>

          {/* Right */}
          <div className="flex flex-col gap-4">
            <p className="text-[10px] text-neutral-700 uppercase tracking-[0.2em]">Connect</p>
            <div className="flex gap-3">
              {/* LinkedIn — replace href with your profile URL */}
              <a
                href="https://www.linkedin.com/in/nishanshetty/"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="LinkedIn"
                className="flex items-center gap-2.5 px-4 py-2.5 border border-white/[0.08] rounded-lg text-neutral-400 hover:text-white hover:border-white/[0.2] hover:bg-white/[0.03] transition-all text-sm"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
                </svg>
                LinkedIn
              </a>

              {/* GitHub — replace href with your profile URL */}
              <a
                href="https://github.com/nishan2204/ml-portfolio"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="GitHub"
                className="flex items-center gap-2.5 px-4 py-2.5 border border-white/[0.08] rounded-lg text-neutral-400 hover:text-white hover:border-white/[0.2] hover:bg-white/[0.03] transition-all text-sm"
              >
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                GitHub
              </a>
            </div>
          </div>
        </div>

        <div className="border-t border-white/[0.05] pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-[11px] text-neutral-800">Built with Next.js · Deployed on Vercel</p>
          <p className="text-[11px] text-neutral-800">© 2026 All rights reserved</p>
        </div>
      </div>
    </footer>
  )
}
