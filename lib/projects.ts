export interface Project {
  id: number
  slug: string
  title: string
  problem: string
  approach: string
  techStack: string[]
  impact: string[]
  demoLabel: string
}

export const projects: Project[] = [
  {
    id: 1,
    slug: 'scheduling-optimization',
    title: 'Scheduling Optimization Engine',
    problem:
      'Staffing across 25+ locations was inefficient due to varying preferences, coverage needs, and shift constraints - costing the organization in overtime and misallocated resources.',
    approach:
      'Modeled the problem as a constraint program over ~12k decision variables (CP-SAT) with shift-balance, skill-mix, and preference constraints; used a genetic algorithm warm-start to seed CP-SAT and cut solve time below the nightly batch window. SimPy discrete-event simulation stress-tested schedules against demand variability before deployment. Orchestrated on AWS Batch with Step Functions; FastAPI interface for leadership to run what-if scenarios (demand shock, headcount cuts, policy changes).',
    techStack: ['CP-SAT', 'Genetic Algorithms', 'SimPy', 'AWS Batch', 'AWS Step Functions', 'FastAPI', 'Python'],
    impact: [
      '35% improvement in staffing efficiency across 25+ locations',
      'Reduced scheduling conflicts and overtime spend',
      'Solve time under 8 minutes on nightly batch (down from 4+ hours with prior heuristic)',
      'Enabled dynamic decision support for planners',
    ],
    demoLabel: 'What-If Scheduling Simulator',
  },
  {
    id: 2,
    slug: 'revenue-forecasting',
    title: 'Revenue Forecasting & Denial Risk System',
    problem:
      'High denial rates and unpredictable accounts receivable aging caused revenue leakage with no early warning system.',
    approach:
      'ARIMA captured trend and seasonality on the aggregate series; an LSTM modeled residuals against payer-mix and claim-aging features to capture non-linear dynamics ARIMA could not. Walk-forward cross-validation, drift monitoring, and nightly Lambda-triggered retraining on AWS SageMaker with S3-based feature storage. Predictions surfaced in Snowflake dashboards used by finance and operations.',
    techStack: ['ARIMA', 'LSTM', 'Walk-forward CV', 'AWS SageMaker', 'AWS Lambda', 'S3', 'Snowflake', 'Python'],
    impact: [
      '77% reduction in reprocessing costs',
      '25% fewer denials',
      '18% MAPE improvement over prior Prophet baseline',
      'Enabled proactive scenario-based revenue planning',
    ],
    demoLabel: 'Forecast Chart - ARIMA vs LSTM',
  },
  {
    id: 3,
    slug: 'findings-agent',
    title: 'Incidental Findings Follow-up Agent',
    problem:
      'Manual tracking of incidental findings in large volumes of unstructured documents led to missed follow-ups and compliance risk across 25+ locations.',
    approach:
      'LangChain RAG agent over a DynamoDB-indexed corpus of radiology and clinical notes, with LLM inference via AWS Bedrock. Built an evaluation harness measuring extraction precision and recall against a radiologist-labeled gold set, with guardrails for HIPAA-sensitive content and a human-in-the-loop review queue for low-confidence outputs. Integrated into HL7/FHIR-based follow-up scheduling and compliance workflows via FastAPI on SageMaker endpoints.',
    techStack: ['LangChain', 'AWS Bedrock', 'DynamoDB', 'AWS SageMaker', 'Claude API', 'HL7/FHIR', 'Python', 'FastAPI'],
    impact: [
      '30% increase in follow-up compliance',
      '45% reduction in manual review effort',
      '94% extraction precision on radiologist-labeled eval set',
      'Improved safety outcomes at scale',
    ],
    demoLabel: 'Document Analysis Agent - Powered by Claude',
  },
  {
    id: 4,
    slug: 'segmentation-causal',
    title: 'Segmentation, Causal Experimentation & Referral Network Platform',
    problem:
      'Outreach campaigns were generic and underperforming. There was no visibility into which interventions actually caused behavior change, and no map of the referral relationships driving the most value.',
    approach:
      'Three-layer platform: (1) K-Means and hierarchical clustering on PCA-reduced behavioral features, validated with silhouette analysis and bootstrap stability tests; (2) NetworkX referral graph with PageRank-style scoring to surface high-value pathways; (3) X-Learner uplift modeling with CUPED variance reduction to measure causal lift, not correlation. Automated experiment tracking via AWS SageMaker and Lambda.',
    techStack: ['K-Means', 'PCA', 'X-Learner Uplift', 'CUPED', 'NetworkX', 'AWS SageMaker', 'Lambda', 'QuickSight', 'Python'],
    impact: [
      '25% improvement in campaign ROI vs. control',
      'Identified highest-value referral pathways for targeted engagement',
      'Reduced experiment runtime ~40% via CUPED variance reduction',
      'Causal (not correlated) retention lift validated across 3 holdout cohorts',
    ],
    demoLabel: 'Segmentation Explorer + Referral Network Graph',
  },
  {
    id: 5,
    slug: 'insight-narrative',
    title: 'Automated Insight Narrative Generator',
    problem:
      'Analysts spent hours each week manually interpreting dashboards and writing executive summaries - a bottleneck that delayed decisions and did not scale across a growing organization.',
    approach:
      'Agent ingests a structured dataset or dashboard export, runs automated anomaly detection and trend analysis, identifies the 3–5 most significant signals, and generates a polished executive-ready narrative using LLM synthesis. Built with Python, Claude API, and Pandas profiling.',
    techStack: ['Claude API', 'Python', 'Pandas', 'Anomaly Detection', 'LangChain', 'FastAPI'],
    impact: [
      '~70% reduction in analyst reporting time',
      'Consistent insight quality regardless of analyst experience level',
      'Closed the last mile between model output and executive decision',
    ],
    demoLabel: 'Insight Narrative Agent - Powered by Claude',
  },
  {
    id: 6,
    slug: 'iot-predictive-maintenance',
    title: 'IoT Predictive Maintenance & Failure Explanation Agent',
    problem:
      'Fault-driven downtime across 10,000+ IoT-enabled assets was unpredictable and expensive. Technician logs contained valuable diagnostic signal that was never systematically analyzed.',
    approach:
      'Predictive maintenance models trained on sensor telemetry with lifecycle simulation. NLP pipeline extracted root cause patterns from unstructured technician logs and automated fault classification. Agent layer explains predicted failures in plain English with recommended interventions.',
    techStack: ['PyTorch', 'Time-Series ML', 'NLP', 'AWS SageMaker', 'IoT Telemetry', 'Python', 'FastAPI'],
    impact: [
      '22% reduction in fault-driven downtime',
      'Automated root cause classification integrated into operational workflows',
    ],
    demoLabel: 'Live Asset Health Dashboard',
  },
  {
    id: 7,
    slug: 'ab-test-interpreter',
    title: 'A/B Test Interpreter Agent',
    problem:
      'Experiment results were routinely misread by non-technical stakeholders - statistical significance confused with practical significance, peeking bias ignored, and recommendations written without accounting for novelty effects.',
    approach:
      'Agent ingests raw experiment results, runs validity checks (sample ratio mismatch, peeking detection, novelty effect flagging), interprets statistical and practical significance, and writes a plain-English recommendation memo with confidence levels and caveats.',
    techStack: ['Claude API', 'Statistics', 'Python', 'FastAPI', 'Pandas', 'SciPy'],
    impact: [
      'Eliminated systematic misinterpretation of experiment results',
      '60% reduction in time from experiment close to decision',
      'Enabled non-technical teams to act on results independently',
    ],
    demoLabel: 'A/B Result Interpreter - Powered by Claude',
  },
  {
    id: 8,
    slug: 'self-healing-pipeline',
    title: 'Self-Healing Pipeline Agent',
    problem:
      'Data pipeline failures were reactive - teams discovered issues hours after silent data corruption had already propagated downstream into models and dashboards.',
    approach:
      'Monitoring agent wired into Airflow DAGs detects failures and classifies root cause (schema drift, upstream data issue, compute failure, or dependency timeout). Agent either auto-remediates known failure patterns or escalates with a structured incident report.',
    techStack: ['Airflow', 'Python', 'AWS Lambda', 'SNS', 'Great Expectations', 'Claude API'],
    impact: [
      'Reduced mean time to detection from hours to minutes',
      'Eliminated class of silent data corruption failures',
      'Shifted team posture from reactive firefighting to proactive maintenance',
    ],
    demoLabel: 'Pipeline Failure Simulator',
  },
  {
    id: 9,
    slug: 'ltv-churn-cohort',
    title: 'LTV & Churn Cohort Analyzer',
    problem:
      'Churn was being measured in aggregate, masking the fact that specific acquisition cohorts were degrading months before the signal appeared in top-line retention metrics.',
    approach:
      'Cohort segmentation by acquisition channel, behavioral pattern, and tenure. LTV trajectory modeling per cohort with leading indicator identification. Agent surfaces which cohorts are at risk, why, and what intervention historically works for that segment.',
    techStack: ['Python', 'SQL', 'Survival Analysis', 'Snowflake', 'AWS SageMaker', 'QuickSight'],
    impact: [
      'Proactive retention investment 60–90 days before churn materialized in aggregate metrics',
      'Improved campaign targeting efficiency',
      'Improved LTV forecasting accuracy',
    ],
    demoLabel: 'Interactive Cohort Explorer',
  },
  {
    id: 10,
    slug: 'capacity-planning',
    title: 'Capacity Planning Simulation',
    problem:
      'Leadership made capacity decisions based on point estimates, with no visibility into the range of outcomes under different demand or resource scenarios.',
    approach:
      'Monte Carlo simulation engine ingests demand forecasts, resource constraints, and growth assumptions. Runs thousands of scenario iterations and outputs a capacity plan with confidence intervals, break-even thresholds, and a plain-English summary of key tradeoffs.',
    techStack: ['Monte Carlo', 'Python', 'NumPy', 'FastAPI', 'Recharts', 'Claude API'],
    impact: [
      'Replaced gut-feel capacity decisions with probabilistic scenario planning',
      'Enabled leadership to stress-test assumptions before committing capital or headcount',
    ],
    demoLabel: 'Monte Carlo Scenario Simulator',
  },
  {
    id: 11,
    slug: 'eda-quality-agent',
    title: 'Automated EDA & Data Quality Report Agent',
    problem:
      'Every new dataset required hours of manual profiling before any modeling could begin - a recurring tax on every data science project.',
    approach:
      'Agent ingests a raw dataset, profiles distributions, missingness, outliers, correlations, and cardinality. Flags data quality issues with severity scores (critical / warning / info). Outputs a structured report with visualizations and recommended preprocessing steps ranked by impact.',
    techStack: ['Python', 'Pandas', 'Pandas Profiling', 'Claude API', 'FastAPI', 'Recharts'],
    impact: [
      'Reduced dataset onboarding from hours to minutes',
      'Standardized data quality assessment across all projects',
      'Gave non-technical stakeholders visibility into data health before models were built',
    ],
    demoLabel: 'Data Quality Report Agent',
  },
  {
    id: 12,
    slug: 'financial-scenario-planner',
    title: 'Multi-Agent Financial Scenario Planner',
    problem:
      'Financial planning relied on single-point forecasts that could not capture the interdependencies between demand volatility, cost structure, and strategic decisions.',
    approach:
      'Multi-agent system with three specialized agents - a forecasting agent (demand and revenue projections), a risk assessment agent (downside scenario modeling and sensitivity analysis), and a narrative agent (plain-English synthesis). Agents hand off outputs sequentially with a shared state object.',
    techStack: ['Claude API', 'LangChain', 'Python', 'FastAPI', 'NumPy', 'Recharts'],
    impact: [
      'Enabled leadership to stress-test strategic decisions against multiple futures before committing',
      'Replaced static spreadsheet models with a dynamic, explainable scenario planning system',
    ],
    demoLabel: 'Three-Agent Scenario Planner - Powered by Claude',
  },
]
