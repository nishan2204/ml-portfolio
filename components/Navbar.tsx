'use client'

import { useState, useEffect } from 'react'
import { projects } from '@/lib/projects'

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [projectsOpen, setProjectsOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Close mobile menu on route-style hash navigation
  const closeMobile = () => setMobileOpen(false)

  return (
    <>
      <nav
        className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
          scrolled
            ? 'bg-black/95 backdrop-blur-md border-b border-white/[0.06]'
            : 'bg-transparent'
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          {/* Brand — replace "DS Portfolio" with your name */}
          <a href="#top" className="flex items-center gap-1.5 text-sm font-semibold tracking-tight">
            <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-blue-400 via-sky-300 to-emerald-400 bg-clip-text text-transparent">NS</span>
          </a>

          {/* Desktop links */}
          <div className="hidden md:flex items-center gap-7">
            <a
              href="#about"
              className="text-sm text-neutral-500 hover:text-white transition-colors duration-150"
            >
              About
            </a>

            {/* Projects dropdown */}
            <div
              className="relative"
              onMouseEnter={() => setProjectsOpen(true)}
              onMouseLeave={() => setProjectsOpen(false)}
            >
              <button className="flex items-center gap-1 text-sm text-neutral-500 hover:text-white transition-colors duration-150">
                Projects
                <svg
                  className={`w-3 h-3 transition-transform duration-200 ${projectsOpen ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              <div
                className={`absolute top-full right-0 mt-3 w-[500px] bg-[#0a0a0a] border border-white/[0.08] rounded-xl shadow-2xl p-2 grid grid-cols-2 gap-0.5 transition-all duration-150 ${
                  projectsOpen ? 'opacity-100 visible translate-y-0' : 'opacity-0 invisible -translate-y-1'
                }`}
              >
                {projects.map((p) => (
                  <a
                    key={p.id}
                    href={`#project-${p.id}`}
                    onClick={() => setProjectsOpen(false)}
                    className="flex items-start gap-2.5 px-3 py-2.5 rounded-lg hover:bg-white/[0.05] transition-colors group"
                  >
                    <span className="text-[10px] text-neutral-700 font-mono mt-0.5 shrink-0 group-hover:text-neutral-500 transition-colors">
                      {String(p.id).padStart(2, '0')}
                    </span>
                    <span className="text-xs text-neutral-500 group-hover:text-neutral-200 leading-snug transition-colors">
                      {p.title}
                    </span>
                  </a>
                ))}
              </div>
            </div>

            <a
              href="#contact"
              className="text-sm text-neutral-500 hover:text-white transition-colors duration-150"
            >
              Contact
            </a>

            <a
              href="/resume.pdf"
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-neutral-500 hover:text-white transition-colors duration-150"
            >
              Resume
            </a>

            <a
              href="#contact"
              className="px-4 py-1.5 text-sm font-medium bg-white text-black rounded-lg hover:bg-neutral-100 transition-colors duration-150"
            >
              Hire Me
            </a>
          </div>

          {/* Mobile hamburger */}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="md:hidden p-2 -mr-2 text-neutral-400 hover:text-white transition-colors"
            aria-label="Toggle menu"
          >
            {mobileOpen ? (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            ) : (
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {/* Mobile menu overlay */}
      {mobileOpen && (
        <div className="fixed inset-0 z-[49] bg-black pt-16 overflow-y-auto">
          <div className="px-6 py-8">
            <a
              href="#about"
              onClick={closeMobile}
              className="flex items-center py-4 text-base text-neutral-300 border-b border-white/[0.06] hover:text-white transition-colors"
            >
              About
            </a>
            <p className="pt-6 pb-3 text-[10px] text-neutral-700 uppercase tracking-[0.2em]">
              Projects
            </p>
            <div className="space-y-0.5">
              {projects.map((p) => (
                <a
                  key={p.id}
                  href={`#project-${p.id}`}
                  onClick={closeMobile}
                  className="flex items-center gap-3 py-2.5 px-2 rounded-lg hover:bg-white/[0.04] transition-colors"
                >
                  <span className="text-xs font-mono text-neutral-700 w-5 shrink-0">
                    {String(p.id).padStart(2, '0')}
                  </span>
                  <span className="text-sm text-neutral-400 hover:text-white">{p.title}</span>
                </a>
              ))}
            </div>
            <div className="mt-8 pt-6 border-t border-white/[0.06]">
              <a
                href="#contact"
                onClick={closeMobile}
                className="block w-full py-3 text-center bg-white text-black font-semibold rounded-lg text-sm"
              >
                Contact / Hire Me
              </a>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
