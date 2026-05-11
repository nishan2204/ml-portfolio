const SKILLS = [
  'Python',
  'SQL',
  'AWS SageMaker',
  'Snowflake',
  'Airflow',
  'MLflow',
  'LangChain',
  'FastAPI',
  'Databricks',
  'PyTorch',
  'TensorFlow',
  'AWS Bedrock',
  'Claude API',
]

export default function SkillsBar() {
  // Duplicate array so the seamless marquee can loop
  const doubled = [...SKILLS, ...SKILLS]

  return (
    <div className="border-y border-white/[0.05] py-5 overflow-hidden relative">
      {/* Fade edges */}
      <div className="pointer-events-none absolute left-0 top-0 bottom-0 w-16 bg-gradient-to-r from-black to-transparent z-10" />
      <div className="pointer-events-none absolute right-0 top-0 bottom-0 w-16 bg-gradient-to-l from-black to-transparent z-10" />

      <div className="flex animate-marquee whitespace-nowrap will-change-transform">
        {doubled.map((skill, i) => (
          <span
            key={i}
            className="mx-8 text-[11px] text-neutral-700 font-mono tracking-[0.15em] uppercase shrink-0"
          >
            {skill}
          </span>
        ))}
      </div>
    </div>
  )
}
