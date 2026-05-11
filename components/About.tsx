import Image from 'next/image'

const INTERESTS = [
  'Travel',
  'Europe',
  'Greek mythology',
  'Road trips',
  'Camping',
  'Cooking',
  'Cocktails',
  'Local discoveries',
  'TV & film',
  'Sports',
  'Home projects',
  'Detailed itineraries',
]

export default function About() {
  return (
    <section
      id="about"
      className="relative border-t border-white/[0.05] py-28 px-6 overflow-hidden"
    >
      {/* Subtle gradient backdrop */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_60%_40%_at_50%_0%,rgba(59,130,246,0.05),transparent)]" />

      <div className="relative max-w-5xl mx-auto">
        {/* Section label */}
        <div className="flex items-center gap-3 mb-12">
          <span className="text-[10px] text-neutral-500 uppercase tracking-[0.25em]">About me</span>
          <span className="h-px flex-1 bg-white/[0.06]" />
        </div>

        <div className="grid md:grid-cols-[minmax(0,_5fr)_minmax(0,_7fr)] gap-10 md:gap-14 items-start">
          {/* Photo column */}
          <div className="md:sticky md:top-28">
            <div className="relative rounded-2xl overflow-hidden border border-white/[0.08] bg-white/[0.02] shadow-2xl">
              <Image
                src="/me.jpeg"
                alt="Nishan Shetty"
                width={600}
                height={800}
                className="w-full h-auto object-cover"
                priority
              />
              {/* Subtle gradient at bottom for depth */}
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/30 to-transparent" />
            </div>
            <p className="mt-3 text-[10px] text-neutral-700 uppercase tracking-[0.2em]">
              Mt. Rainier · 2024
            </p>
          </div>

          {/* Text column */}
          <div>
            {/* Lead paragraph */}
            <p className="text-xl md:text-2xl text-neutral-200 leading-relaxed font-light tracking-tight mb-8">
              I&apos;m a data scientist and AI engineer who likes building systems that are{' '}
              <span className="text-white">practical, explainable, and actually useful</span> in the
              real world. Most of my professional work sits at the intersection of machine learning,
              operations, healthcare, and decision support. Outside of work I&apos;m usually drawn to
              things that involve exploration, creativity, and learning how systems work.
            </p>

            {/* Body paragraphs */}
            <div className="space-y-5 text-base text-neutral-400 leading-relaxed">
              <p>
                I like to travel, especially through Europe, and I&apos;m always interested in places
                with history, architecture, good food, and a little bit of mythology or mystery.
                Greece is high on my list, partly because I grew up fascinated by Greek mythology. I
                also enjoy road trips, camping, trying new recipes, making cocktails, and finding
                interesting local spots when I&apos;m in a new city.
              </p>
              <p>
                A lot of my interests overlap with how I approach data science: patterns, stories,
                constraints, tradeoffs, and building something useful from messy inputs. Whether
                I&apos;m planning a trip, cooking, styling a space, or designing an AI workflow,
                I&apos;m usually thinking about how the pieces fit together.
              </p>
              <p>
                Outside of that, I&apos;m into TV, movies, sports, home projects, and the occasional
                overly detailed itinerary. I&apos;m happiest when I&apos;m learning something new,
                solving a practical problem, or turning a vague idea into something tangible.
              </p>
            </div>
          </div>
        </div>

        {/* Interests pills — full width below */}
        <div className="mt-14 pt-10 border-t border-white/[0.04]">
          <p className="text-[10px] text-neutral-700 uppercase tracking-[0.25em] mb-4">
            Off the clock
          </p>
          <div className="flex flex-wrap gap-2">
            {INTERESTS.map((tag) => (
              <span
                key={tag}
                className="text-[11px] px-3 py-1.5 rounded-full border border-white/[0.08] text-neutral-400 bg-white/[0.02] hover:border-white/[0.15] hover:text-neutral-200 transition-colors"
              >
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
