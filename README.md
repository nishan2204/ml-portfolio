# Nishan Shetty — DS Portfolio

Personal portfolio showcasing 12 production ML and AI engineering projects.

**Live:** [nishanshetty.com](https://nishanshetty.com)

---

## Projects

### 01 · Scheduling Optimization Engine

Staffing optimization across 25+ locations with varying shift preferences, coverage requirements, and operational constraints.

**Models & Approach:** Constraint programming via Google OR-Tools CP-SAT, genetic algorithms for multi-objective optimization, discrete-event simulation with SimPy for scenario validation. Hill-climbing local search for real-time what-if queries.

**Stack:** Python · OR-Tools · SimPy · AWS Batch · AWS Step Functions · FastAPI

---

### 02 · Revenue Forecasting & Denial Risk System

Hybrid forecasting system for denial volume prediction and accounts receivable aging with nightly automated retraining.

**Models & Approach:** ARIMA with seasonal decomposition for baseline trend modeling, Bidirectional LSTM with attention for capturing non-linear seasonal patterns. Ensemble outputs weighted by rolling forecast accuracy. Feature store on S3 with Lambda-triggered retraining pipeline.

**Stack:** Python · ARIMA · Bi-LSTM · AWS SageMaker · AWS Lambda · S3 · Snowflake

---

### 03 · Incidental Findings Follow-up Agent

RAG-powered agent that extracts, classifies, and routes incidental findings from unstructured clinical documents across 25+ locations.

**Models & Approach:** LangChain RAG pipeline with LLM inference via AWS Bedrock for document understanding. DynamoDB for retrieval indexing. Urgency classification (routine / soon / urgent) with structured follow-up generation. Claude API for interactive demo.

**Stack:** Python · LangChain · AWS Bedrock · DynamoDB · AWS SageMaker · Claude API · FastAPI

---

### 04 · Segmentation, Causal Experimentation & Referral Network Platform

Three-layer analytics platform combining unsupervised segmentation, graph-based network analysis, and causal inference.

**Models & Approach:** K-Means and hierarchical clustering with PCA for dimensionality reduction and customer segmentation. NetworkX graph modeling to identify high-value referral pathways and at-risk relationships. Uplift modeling (T-learner / X-learner meta-learners) with causal inference to measure true intervention impact beyond correlation.

**Stack:** Python · scikit-learn · NetworkX · Uplift Modeling · AWS SageMaker · AWS Lambda · Amazon QuickSight

---

### 05 · Automated Insight Narrative Generator

End-to-end agent that ingests structured data, detects signals, and generates polished executive narratives without analyst intervention.

**Models & Approach:** Automated anomaly detection using z-score and IQR methods with trend decomposition via statsmodels. Top-signal ranking by effect size and statistical significance. LLM synthesis via Claude API to generate context-aware, executive-ready summaries.

**Stack:** Python · Pandas · statsmodels · Claude API · LangChain · FastAPI

---

### 06 · IoT Predictive Maintenance & Failure Explanation Agent

Predictive failure detection and root cause explanation across 10,000+ IoT-enabled assets.

**Models & Approach:** PyTorch time-series models (TCN and LSTM-Autoencoder) trained on sensor telemetry for anomaly and failure prediction. NLP pipeline using transformer-based classification to extract root cause patterns from unstructured technician logs. Agent layer generates plain-English failure explanations with recommended interventions.

**Stack:** Python · PyTorch · TCN · LSTM-Autoencoder · HuggingFace Transformers · AWS SageMaker · FastAPI

---

### 07 · A/B Test Interpreter Agent

Automated experiment analysis agent that runs statistical validity checks and produces recommendation memos for non-technical stakeholders.

**Models & Approach:** Sequential validity checks — sample ratio mismatch detection, peeking bias correction (always-valid inference via mSPRT), novelty effect flagging via time-decay analysis. Cohen's d and CATE for practical significance. Claude API synthesizes findings into a structured recommendation memo with confidence ratings.

**Stack:** Python · SciPy · statsmodels · Claude API · Pandas · FastAPI

---

### 08 · Self-Healing Pipeline Agent

Monitoring agent wired into Airflow DAGs that detects, classifies, and remediates data pipeline failures in real time.

**Models & Approach:** Rule-based failure classifier covering schema drift, upstream data issues, compute failures, and dependency timeouts. Great Expectations for data contract validation. Auto-remediation for known failure patterns; Claude API generates structured incident reports with downstream impact analysis for novel failures.

**Stack:** Python · Apache Airflow · Great Expectations · AWS Lambda · Amazon SNS · Claude API

---

### 09 · LTV & Churn Cohort Analyzer

Cohort-level LTV trajectory modeling that surfaces degrading segments 60-90 days before churn appears in aggregate metrics.

**Models & Approach:** Kaplan-Meier survival curves and Cox Proportional Hazards modeling per acquisition cohort. Leading indicator identification via Granger causality testing. Segment-level intervention recommendation based on historical response rates by cohort type.

**Stack:** Python · lifelines · SciPy · SQL · Snowflake · AWS SageMaker · Amazon QuickSight

---

### 10 · Capacity Planning Simulation

Monte Carlo simulation engine that replaces point-estimate capacity decisions with probabilistic scenario planning.

**Models & Approach:** 10,000-iteration Monte Carlo simulation with correlated random draws across demand, cost, and growth variables. Outputs confidence intervals, break-even thresholds, and tail-risk quantiles. Claude API synthesizes simulation output into plain-English tradeoff summaries for leadership.

**Stack:** Python · NumPy · SciPy · Monte Carlo simulation · Claude API · FastAPI

---

### 11 · Automated EDA & Data Quality Report Agent

Automated dataset profiling agent that replaces manual exploratory analysis with a structured, severity-ranked data quality report.

**Models & Approach:** Distribution profiling, missingness pattern detection (MCAR/MAR/MNAR classification), outlier detection via Isolation Forest and IQR, correlation analysis with redundancy flagging, cardinality assessment for categorical features. Issues ranked by modeling impact severity (critical / warning / info).

**Stack:** Python · Pandas · scikit-learn · Isolation Forest · Claude API · FastAPI

---

### 12 · Multi-Agent Financial Scenario Planner

Three-agent system for stress-testing strategic financial decisions against multiple demand and cost futures.

**Models & Approach:** Forecasting agent uses ARIMA and exponential smoothing for demand and revenue projections. Risk agent runs sensitivity analysis and downside scenario modeling with VaR-style tail risk quantification. Narrative agent (Claude API) synthesizes all outputs into a coherent executive scenario report. Agents share a structured state object with sequential handoffs.

**Stack:** Python · LangChain · Claude API · ARIMA · NumPy · FastAPI

