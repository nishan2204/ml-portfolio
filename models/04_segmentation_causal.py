"""
Segmentation, Causal Experimentation & Referral Network Platform
K-Means + hierarchical clustering, NetworkX referral graph analysis,
and X-Learner uplift modeling with CUPED variance reduction.
"""

import numpy as np
import pandas as pd
import networkx as nx
import boto3
from dataclasses import dataclass
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans, AgglomerativeClustering
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from scipy.stats import ttest_ind
from scipy.spatial.distance import cdist
from econml.metalearners import XLearner
from econml.dml import LinearDML
from sklearn.ensemble import GradientBoostingRegressor, GradientBoostingClassifier
from sklearn.linear_model import Ridge


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PCA_VARIANCE_THRESHOLD = 0.90
MAX_CLUSTERS = 12
BOOTSTRAP_STABILITY_REPS = 50
CUPED_COVARIATE = "pre_period_metric"
PAGERANK_ALPHA = 0.85
REFERRAL_EDGE_WEIGHT_THRESHOLD = 2   # minimum referral events to include edge


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_behavioral_features(snowflake_conn, cohort_date: str) -> pd.DataFrame:
    query = f"""
        SELECT
            patient_id,
            acquisition_channel,
            visit_frequency_90d,
            avg_days_between_visits,
            service_diversity_score,
            nps_score,
            total_revenue_ltm,
            digital_engagement_score,
            referral_count_outbound,
            referral_count_inbound,
            days_since_last_visit,
            tenure_days
        FROM analytics.patient_behavioral_features
        WHERE snapshot_date = '{cohort_date}'
          AND tenure_days >= 30
    """
    df = pd.read_sql(query, snowflake_conn)
    return df.set_index("patient_id")

def load_referral_events(snowflake_conn, lookback_days: int = 365) -> pd.DataFrame:
    query = f"""
        SELECT referrer_id, referred_id, referral_date, converted
        FROM analytics.referral_events
        WHERE referral_date >= DATEADD(day, -{lookback_days}, CURRENT_DATE)
    """
    return pd.read_sql(query, snowflake_conn)

def load_experiment_data(snowflake_conn, experiment_id: str) -> pd.DataFrame:
    query = f"""
        SELECT
            patient_id,
            treatment_arm,
            pre_period_metric,
            post_period_metric,
            days_in_study,
            acquisition_channel,
            tenure_days
        FROM analytics.experiments
        WHERE experiment_id = '{experiment_id}'
    """
    return pd.read_sql(query, snowflake_conn)


# ---------------------------------------------------------------------------
# Layer 1: Segmentation
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "visit_frequency_90d", "avg_days_between_visits", "service_diversity_score",
    "nps_score", "total_revenue_ltm", "digital_engagement_score",
    "referral_count_outbound", "days_since_last_visit", "tenure_days",
]

@dataclass
class SegmentationResult:
    labels: np.ndarray
    n_clusters: int
    silhouette: float
    cluster_profiles: pd.DataFrame
    pca_components: int
    pca_variance_explained: float
    stability_score: float


def fit_pca(df: pd.DataFrame) -> tuple:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df[FEATURE_COLS].fillna(df[FEATURE_COLS].median()))
    pca = PCA(n_components=None)
    pca.fit(X_scaled)
    cumvar = np.cumsum(pca.explained_variance_ratio_)
    n_components = int(np.argmax(cumvar >= PCA_VARIANCE_THRESHOLD) + 1)
    pca_final = PCA(n_components=n_components)
    X_pca = pca_final.fit_transform(X_scaled)
    return X_pca, scaler, pca_final, cumvar[n_components - 1]


def select_optimal_k(X_pca: np.ndarray) -> tuple:
    scores = {}
    for k in range(3, MAX_CLUSTERS + 1):
        km = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=42)
        labels = km.fit_predict(X_pca)
        scores[k] = silhouette_score(X_pca, labels, sample_size=min(5000, len(X_pca)))
    best_k = max(scores, key=scores.get)
    return best_k, scores[best_k]


def bootstrap_stability(X_pca: np.ndarray, k: int, n_reps: int = BOOTSTRAP_STABILITY_REPS) -> float:
    """Jaccard-based cluster stability via bootstrap resampling."""
    ref_km = KMeans(n_clusters=k, init="k-means++", n_init=10, random_state=42)
    ref_labels = ref_km.fit_predict(X_pca)
    ref_centers = ref_km.cluster_centers_

    stabilities = []
    for rep in range(n_reps):
        idx = np.random.choice(len(X_pca), size=len(X_pca), replace=True)
        boot_km = KMeans(n_clusters=k, init="k-means++", n_init=5, random_state=rep)
        boot_labels = boot_km.fit_predict(X_pca[idx])
        # Match clusters by centroid proximity
        dists = cdist(ref_centers, boot_km.cluster_centers_)
        mapping = {}
        for _ in range(k):
            r, c = np.unravel_index(dists.argmin(), dists.shape)
            mapping[c] = r
            dists[r, :] = np.inf
            dists[:, c] = np.inf
        # Compute mean Jaccard across matched clusters
        j_scores = []
        for boot_c, ref_c in mapping.items():
            a = set(idx[boot_labels == boot_c])
            b = set(np.where(ref_labels == ref_c)[0])
            j_scores.append(len(a & b) / len(a | b) if a | b else 0)
        stabilities.append(np.mean(j_scores))
    return float(np.mean(stabilities))


def run_segmentation(df: pd.DataFrame) -> SegmentationResult:
    X_pca, _, _, var_explained = fit_pca(df)
    best_k, sil_score = select_optimal_k(X_pca)
    stability = bootstrap_stability(X_pca, best_k)

    km = KMeans(n_clusters=best_k, init="k-means++", n_init=10, random_state=42)
    labels = km.fit_predict(X_pca)

    df_labeled = df.copy()
    df_labeled["segment"] = labels
    profiles = df_labeled.groupby("segment")[FEATURE_COLS].agg(["mean", "median"])

    return SegmentationResult(
        labels=labels,
        n_clusters=best_k,
        silhouette=sil_score,
        cluster_profiles=profiles,
        pca_components=X_pca.shape[1],
        pca_variance_explained=var_explained,
        stability_score=stability,
    )


# ---------------------------------------------------------------------------
# Layer 2: Referral network analysis
# ---------------------------------------------------------------------------

@dataclass
class NetworkResult:
    high_value_nodes: list[str]
    at_risk_nodes: list[str]
    community_map: dict
    pagerank_scores: dict
    graph_density: float
    avg_path_length: float


def build_referral_graph(events_df: pd.DataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    edge_counts = (
        events_df.groupby(["referrer_id", "referred_id"])
        .agg(weight=("converted", "sum"), volume=("converted", "count"))
        .reset_index()
    )
    for _, row in edge_counts[edge_counts["volume"] >= REFERRAL_EDGE_WEIGHT_THRESHOLD].iterrows():
        G.add_edge(row["referrer_id"], row["referred_id"],
                   weight=row["weight"], volume=row["volume"])
    return G


def analyze_referral_network(events_df: pd.DataFrame) -> NetworkResult:
    G = build_referral_graph(events_df)
    pagerank = nx.pagerank(G, alpha=PAGERANK_ALPHA, weight="weight")

    pr_series = pd.Series(pagerank)
    high_value = pr_series[pr_series > pr_series.quantile(0.90)].index.tolist()

    # Nodes with high in-degree but declining recent referrals (at-risk)
    in_degrees = dict(G.in_degree(weight="weight"))
    recent_mask = events_df["referral_date"] >= (
        pd.Timestamp.today() - pd.Timedelta(days=30)
    ).strftime("%Y-%m-%d")
    recent_counts = events_df[recent_mask].groupby("referrer_id").size()
    historical_avg = events_df.groupby("referrer_id").size() / 12
    at_risk = [
        n for n in G.nodes()
        if in_degrees.get(n, 0) > np.percentile(list(in_degrees.values()), 75)
        and recent_counts.get(n, 0) < historical_avg.get(n, 0) * 0.5
    ]

    undirected = G.to_undirected()
    communities = nx.community.greedy_modularity_communities(undirected)
    community_map = {
        node: i for i, comm in enumerate(communities) for node in comm
    }

    connected = nx.weakly_connected_components(G)
    largest_cc = G.subgraph(max(connected, key=len))
    try:
        avg_path = nx.average_shortest_path_length(largest_cc.to_undirected())
    except Exception:
        avg_path = float("nan")

    return NetworkResult(
        high_value_nodes=high_value,
        at_risk_nodes=at_risk,
        community_map=community_map,
        pagerank_scores=pagerank,
        graph_density=nx.density(G),
        avg_path_length=avg_path,
    )


# ---------------------------------------------------------------------------
# Layer 3: Causal inference — X-Learner with CUPED
# ---------------------------------------------------------------------------

@dataclass
class UpliftResult:
    cate_estimates: np.ndarray
    ate: float
    ate_std: float
    ate_pvalue: float
    cuped_variance_reduction_pct: float
    top_treated_ids: list


def cuped_adjust(df: pd.DataFrame, outcome_col: str, covariate_col: str) -> pd.Series:
    """CUPED: partial out pre-period covariate to reduce variance."""
    theta = np.cov(df[outcome_col], df[covariate_col])[0, 1] / np.var(df[covariate_col])
    adjusted = df[outcome_col] - theta * (df[covariate_col] - df[covariate_col].mean())
    return adjusted


def run_uplift_model(exp_df: pd.DataFrame) -> UpliftResult:
    # CUPED adjustment
    raw_var = exp_df["post_period_metric"].var()
    exp_df["outcome_cuped"] = cuped_adjust(
        exp_df, "post_period_metric", CUPED_COVARIATE
    )
    cuped_var = exp_df["outcome_cuped"].var()
    variance_reduction = (1 - cuped_var / raw_var) * 100

    feature_cols = ["tenure_days", "visit_frequency_90d", "service_diversity_score",
                    "digital_engagement_score", "pre_period_metric"]
    X = exp_df[feature_cols].fillna(0).values
    T = (exp_df["treatment_arm"] == "treatment").astype(int).values
    Y = exp_df["outcome_cuped"].values

    # X-Learner
    xlr = XLearner(
        models=GradientBoostingRegressor(n_estimators=200, max_depth=4, random_state=42),
        propensity_model=GradientBoostingClassifier(n_estimators=100, random_state=42),
    )
    xlr.fit(Y, T, X)
    cate = xlr.effect(X)

    # ATE and significance
    ctrl = exp_df.loc[T == 0, "outcome_cuped"].values
    trt = exp_df.loc[T == 1, "outcome_cuped"].values
    t_stat, pvalue = ttest_ind(trt, ctrl)

    top_ids = (
        exp_df.assign(cate=cate)
        .nlargest(100, "cate")["patient_id"]
        .tolist()
        if "patient_id" in exp_df.columns else []
    )

    return UpliftResult(
        cate_estimates=cate,
        ate=float(cate.mean()),
        ate_std=float(cate.std()),
        ate_pvalue=float(pvalue),
        cuped_variance_reduction_pct=float(variance_reduction),
        top_treated_ids=top_ids,
    )


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def run_pipeline(behavioral_df: pd.DataFrame, referral_df: pd.DataFrame,
                 experiment_df: pd.DataFrame) -> dict:
    print("Layer 1/3 — Segmentation...")
    seg = run_segmentation(behavioral_df)
    print(f"  Optimal clusters: {seg.n_clusters} (silhouette={seg.silhouette:.3f}, "
          f"stability={seg.stability_score:.3f})")

    print("Layer 2/3 — Referral network analysis...")
    net = analyze_referral_network(referral_df)
    print(f"  High-value nodes: {len(net.high_value_nodes)}, "
          f"At-risk: {len(net.at_risk_nodes)}")

    print("Layer 3/3 — X-Learner uplift modeling...")
    uplift = run_uplift_model(experiment_df)
    print(f"  ATE: {uplift.ate:.4f} (p={uplift.ate_pvalue:.4f})")
    print(f"  CUPED variance reduction: {uplift.cuped_variance_reduction_pct:.1f}%")

    return {
        "segmentation": seg,
        "network": net,
        "uplift": uplift,
    }


if __name__ == "__main__":
    np.random.seed(42)
    n = 2000

    behavioral_df = pd.DataFrame({
        col: np.random.randn(n)
        for col in FEATURE_COLS
    })

    referral_df = pd.DataFrame({
        "referrer_id": np.random.choice([f"P{i:04d}" for i in range(500)], n),
        "referred_id": np.random.choice([f"P{i:04d}" for i in range(500)], n),
        "referral_date": pd.date_range("2024-01-01", periods=n, freq="h").strftime("%Y-%m-%d"),
        "converted": np.random.binomial(1, 0.4, n),
    })

    experiment_df = pd.DataFrame({
        "patient_id": [f"P{i:04d}" for i in range(n)],
        "treatment_arm": np.random.choice(["control", "treatment"], n),
        "pre_period_metric": np.random.normal(50, 10, n),
        "post_period_metric": np.random.normal(52, 10, n),
        "tenure_days": np.random.randint(30, 1000, n),
        "visit_frequency_90d": np.random.randint(1, 20, n),
        "service_diversity_score": np.random.uniform(0, 1, n),
        "digital_engagement_score": np.random.uniform(0, 1, n),
    })

    results = run_pipeline(behavioral_df, referral_df, experiment_df)
