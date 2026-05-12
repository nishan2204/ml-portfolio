const SKILLS = [
  'Python',
  'SQL',
  'R',
  'Scikit-learn',
  'PyTorch',
  'TensorFlow',
  'XGBoost',
  'LightGBM',
  'Hugging Face',
  'LangChain',
  'AWS Bedrock',
  'RAG',
  'Prompt Engineering',
  'MCP',
  'AWS SageMaker',
  'MLflow',
  'Airflow',
  'Docker',
  'CI/CD',
  'FastAPI',
  'AWS Lambda',
  'Snowflake',
  'Databricks',
  'Spark',
  'dbt',
  'Pandas',
  'SQL Server',
  'AWS',
  'Azure',
  'Tableau',
  'Power BI',
  'spaCy',
  'NLTK',
  'Transformers',
  'NER',
  'Causal Inference',
  'A/B Testing',
  'Time Series Forecasting',
  'Uplift Modeling',
  'Graph Models',
  'Optimization',
  'Monte Carlo Simulation',
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
