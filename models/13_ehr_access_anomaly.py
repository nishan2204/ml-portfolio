"""
Suspicious EHR Access Detection
Per-user behavioral baseline modeling, Isolation Forest + LSTM Autoencoder
on access sequences, and graph-based care relationship violation detection.
Real-time risk scoring via Kafka with tiered alerting.
"""

import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
import networkx as nx
import boto3
from kafka import KafkaConsumer, KafkaProducer
from fastapi import FastAPI
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ISOLATION_FOREST_CONTAMINATION = 0.03
LSTM_AE_HIDDEN = 64
LSTM_AE_LAYERS = 2
SEQUENCE_LENGTH = 20            # access events per session window
ANOMALY_THRESHOLD_ISO = 0.55    # Isolation Forest score threshold
ANOMALY_THRESHOLD_LSTM = 0.60   # LSTM reconstruction error threshold
RISK_WEIGHTS = {"iso": 0.40, "lstm": 0.35, "graph": 0.25}
CARE_RELATIONSHIP_LOOKBACK_DAYS = 90
KAFKA_TOPIC_IN = "ehr-access-events"
KAFKA_TOPIC_OUT = "ehr-access-alerts"
SAGEMAKER_ENDPOINT = "ehr-anomaly-scorer"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AccessEvent:
    event_id: str
    user_id: str
    role: str
    department: str
    patient_id: str
    record_type: str
    access_timestamp: str
    hour_of_day: int
    day_of_week: int
    session_record_count: int
    days_since_last_clinical_note: int
    in_care_relationship: bool
    location_id: str

@dataclass
class RiskScore:
    event_id: str
    user_id: str
    patient_id: str
    iso_score: float
    lstm_score: float
    graph_flag: bool
    combined_score: float
    risk_tier: str              # "low" | "elevated" | "high"
    risk_factors: list[str]
    requires_alert: bool


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "hour_of_day",
    "day_of_week",
    "session_record_count",
    "days_since_last_clinical_note",
    "in_care_relationship",
    "is_after_hours",
    "volume_z_vs_user_baseline",
    "timing_z_vs_user_baseline",
    "record_type_encoded",
    "role_encoded",
]

ROLE_MAP = {"Physician": 0, "RN": 1, "Admin": 2, "Lab Tech": 3, "Pharmacist": 4}
RECORD_TYPE_MAP = {"Clinical Note": 0, "Lab Result": 1, "Imaging": 2,
                   "Medication": 3, "Billing": 4, "Discharge Summary": 5}
AFTER_HOURS = {
    "Physician": (21, 7), "RN": (22, 6), "Admin": (18, 8),
    "Lab Tech": (20, 6), "Pharmacist": (22, 6),
}


class UserBaselineTracker:
    """Rolling per-user statistics for z-score feature computation."""

    def __init__(self, window: int = 500):
        self.window = window
        self._volume_history: dict[str, list[float]] = defaultdict(list)
        self._hour_history: dict[str, list[float]] = defaultdict(list)

    def update(self, user_id: str, session_count: int, hour: int):
        self._volume_history[user_id].append(session_count)
        self._hour_history[user_id].append(hour)
        if len(self._volume_history[user_id]) > self.window:
            self._volume_history[user_id].pop(0)
            self._hour_history[user_id].pop(0)

    def volume_z(self, user_id: str, session_count: int) -> float:
        hist = self._volume_history.get(user_id, [session_count])
        mu, sigma = np.mean(hist), np.std(hist)
        return float((session_count - mu) / max(sigma, 1e-6))

    def timing_z(self, user_id: str, hour: int) -> float:
        hist = self._hour_history.get(user_id, [hour])
        mu, sigma = np.mean(hist), np.std(hist)
        return float((hour - mu) / max(sigma, 1e-6))


def engineer_features(event: AccessEvent, baseline: UserBaselineTracker) -> dict:
    after_hours_bounds = AFTER_HOURS.get(event.role, (22, 6))
    is_after_hours = (event.hour_of_day >= after_hours_bounds[0] or
                      event.hour_of_day < after_hours_bounds[1])

    features = {
        "hour_of_day": event.hour_of_day,
        "day_of_week": event.day_of_week,
        "session_record_count": event.session_record_count,
        "days_since_last_clinical_note": event.days_since_last_clinical_note,
        "in_care_relationship": int(event.in_care_relationship),
        "is_after_hours": int(is_after_hours),
        "volume_z_vs_user_baseline": baseline.volume_z(event.user_id, event.session_record_count),
        "timing_z_vs_user_baseline": baseline.timing_z(event.user_id, event.hour_of_day),
        "record_type_encoded": RECORD_TYPE_MAP.get(event.record_type, -1),
        "role_encoded": ROLE_MAP.get(event.role, -1),
    }
    baseline.update(event.user_id, event.session_record_count, event.hour_of_day)
    return features


# ---------------------------------------------------------------------------
# Model 1: Isolation Forest — point anomaly detection
# ---------------------------------------------------------------------------

class IsolationForestScorer:
    def __init__(self):
        self.model = IsolationForest(
            contamination=ISOLATION_FOREST_CONTAMINATION,
            n_estimators=200,
            max_samples="auto",
            random_state=42,
            n_jobs=-1,
        )
        self.scaler = StandardScaler()
        self._fitted = False

    def fit(self, feature_df: pd.DataFrame):
        X = feature_df[FEATURE_COLS].fillna(0).values
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self._fitted = True
        print(f"Isolation Forest fitted on {len(X)} events")

    def score(self, features: dict) -> float:
        """Returns anomaly score 0–1 (higher = more anomalous)."""
        if not self._fitted:
            raise RuntimeError("Model not fitted")
        X = np.array([[features.get(c, 0) for c in FEATURE_COLS]])
        X_scaled = self.scaler.transform(X)
        # decision_function returns negative scores; convert to 0-1 anomaly score
        raw = self.model.decision_function(X_scaled)[0]
        normalized = 1 / (1 + np.exp(5 * raw))  # sigmoid inversion
        return float(np.clip(normalized, 0, 1))


# ---------------------------------------------------------------------------
# Model 2: LSTM Autoencoder — sequential session anomaly detection
# ---------------------------------------------------------------------------

class SessionDataset(Dataset):
    def __init__(self, sequences: np.ndarray):
        self.X = torch.FloatTensor(sequences)

    def __len__(self): return len(self.X)
    def __getitem__(self, idx): return self.X[idx]


class LSTMAutoencoder(nn.Module):
    def __init__(self, input_size: int = len(FEATURE_COLS),
                 hidden_size: int = LSTM_AE_HIDDEN,
                 num_layers: int = LSTM_AE_LAYERS):
        super().__init__()
        self.encoder = nn.LSTM(input_size, hidden_size, num_layers,
                               batch_first=True, dropout=0.1)
        self.decoder = nn.LSTM(hidden_size, hidden_size, num_layers,
                               batch_first=True, dropout=0.1)
        self.output = nn.Linear(hidden_size, input_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, c) = self.encoder(x)
        repeated = h[-1].unsqueeze(1).repeat(1, x.size(1), 1)
        decoded, _ = self.decoder(repeated, (h, c))
        return self.output(decoded)


class LSTMAnomalyScorer:
    def __init__(self):
        self.model = LSTMAutoencoder()
        self.scaler = StandardScaler()
        self._threshold = 0.5
        self._fitted = False

    def _build_sequences(self, feature_df: pd.DataFrame) -> np.ndarray:
        X = self.scaler.fit_transform(feature_df[FEATURE_COLS].fillna(0).values)
        sequences = []
        for i in range(SEQUENCE_LENGTH, len(X) + 1):
            sequences.append(X[i - SEQUENCE_LENGTH:i])
        return np.array(sequences) if sequences else np.empty((0, SEQUENCE_LENGTH, len(FEATURE_COLS)))

    def fit(self, feature_df: pd.DataFrame, epochs: int = 30, batch_size: int = 64):
        sequences = self._build_sequences(feature_df)
        if len(sequences) == 0:
            return
        dataset = SessionDataset(sequences)
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

        optimizer = torch.optim.Adam(self.model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        self.model.train()
        for epoch in range(epochs):
            losses = []
            for (X_b,) in loader:
                optimizer.zero_grad()
                recon = self.model(X_b)
                loss = criterion(recon, X_b)
                loss.backward()
                optimizer.step()
                losses.append(loss.item())
            if (epoch + 1) % 10 == 0:
                print(f"  LSTM AE epoch {epoch+1}/{epochs} — loss: {np.mean(losses):.4f}")

        # Set threshold at 95th percentile of training reconstruction errors
        self.model.eval()
        recon_errors = []
        with torch.no_grad():
            for (X_b,) in DataLoader(dataset, batch_size=256):
                recon = self.model(X_b)
                mse = nn.MSELoss(reduction="none")(recon, X_b).mean(dim=(1, 2))
                recon_errors.extend(mse.numpy())
        self._threshold = float(np.percentile(recon_errors, 95))
        self._fitted = True
        print(f"LSTM AE threshold set at p95: {self._threshold:.4f}")

    def score(self, session_sequence: np.ndarray) -> float:
        """Score a single session sequence. Returns 0-1 anomaly score."""
        self.model.eval()
        with torch.no_grad():
            x = torch.FloatTensor(
                self.scaler.transform(session_sequence)
            ).unsqueeze(0)
            recon = self.model(x)
            mse = float(nn.MSELoss()(recon, x).item())
        return float(np.clip(mse / max(self._threshold * 2, 1e-6), 0, 1))


# ---------------------------------------------------------------------------
# Model 3: Graph — care relationship violation detection
# ---------------------------------------------------------------------------

class CareRelationshipGraph:
    """
    Bipartite graph: provider nodes ↔ patient nodes.
    Edges represent documented clinical encounters.
    Access events with no edge = care relationship violation.
    """

    def __init__(self):
        self.G = nx.Graph()

    def build_from_encounters(self, encounters_df: pd.DataFrame):
        """encounters_df: columns [provider_id, patient_id, encounter_date]"""
        self.G.clear()
        cutoff = pd.Timestamp.today() - pd.Timedelta(days=CARE_RELATIONSHIP_LOOKBACK_DAYS)
        recent = encounters_df[pd.to_datetime(encounters_df["encounter_date"]) >= cutoff]
        for _, row in recent.iterrows():
            self.G.add_edge(f"P:{row['provider_id']}", f"PT:{row['patient_id']}",
                            last_encounter=row["encounter_date"])

    def has_care_relationship(self, user_id: str, patient_id: str) -> bool:
        return self.G.has_edge(f"P:{user_id}", f"PT:{patient_id}")

    def flag_violation(self, event: AccessEvent) -> bool:
        high_risk_roles = {"Physician", "RN", "Pharmacist"}
        if event.role not in high_risk_roles:
            return False
        return not self.has_care_relationship(event.user_id, event.patient_id)


# ---------------------------------------------------------------------------
# Risk scoring + factor attribution
# ---------------------------------------------------------------------------

def compute_risk(event: AccessEvent, iso_score: float,
                 lstm_score: float, graph_flag: bool,
                 features: dict) -> RiskScore:
    combined = (
        RISK_WEIGHTS["iso"] * iso_score +
        RISK_WEIGHTS["lstm"] * lstm_score +
        RISK_WEIGHTS["graph"] * (1.0 if graph_flag else 0.0)
    )
    tier = "high" if combined >= 0.55 else "elevated" if combined >= 0.28 else "low"

    factors = []
    if features.get("is_after_hours"):
        factors.append(f"After-hours access ({event.hour_of_day}:00)")
    vol_z = features.get("volume_z_vs_user_baseline", 0)
    if vol_z > 1.5:
        factors.append(f"Session volume {event.session_record_count} records "
                       f"({vol_z:.1f}x above user baseline)")
    if graph_flag:
        factors.append("No documented care relationship in past 90 days")
    if event.days_since_last_clinical_note > 90:
        factors.append(f"Last clinical note {event.days_since_last_clinical_note}d ago")
    if iso_score > ANOMALY_THRESHOLD_ISO:
        factors.append(f"Isolation Forest score {iso_score:.2f} (threshold {ANOMALY_THRESHOLD_ISO})")

    return RiskScore(
        event_id=event.event_id,
        user_id=event.user_id,
        patient_id=event.patient_id,
        iso_score=round(iso_score, 3),
        lstm_score=round(lstm_score, 3),
        graph_flag=graph_flag,
        combined_score=round(combined, 3),
        risk_tier=tier,
        risk_factors=factors,
        requires_alert=tier in ("high", "elevated"),
    )


# ---------------------------------------------------------------------------
# Kafka real-time scoring pipeline
# ---------------------------------------------------------------------------

class RealTimeScoringPipeline:
    def __init__(self, iso_model: IsolationForestScorer,
                 lstm_model: LSTMAnomalyScorer,
                 graph: CareRelationshipGraph,
                 kafka_bootstrap: str = "localhost:9092"):
        self.iso = iso_model
        self.lstm = lstm_model
        self.graph = graph
        self.baseline = UserBaselineTracker()
        self._session_buffers: dict[str, list[dict]] = defaultdict(list)

        self.consumer = KafkaConsumer(
            KAFKA_TOPIC_IN,
            bootstrap_servers=kafka_bootstrap,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
            enable_auto_commit=True,
        )
        self.producer = KafkaProducer(
            bootstrap_servers=kafka_bootstrap,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        )

    def _get_session_sequence(self, user_id: str, features: dict) -> np.ndarray:
        buf = self._session_buffers[user_id]
        buf.append([features.get(c, 0) for c in FEATURE_COLS])
        if len(buf) > SEQUENCE_LENGTH:
            buf.pop(0)
        seq = np.array(buf)
        if len(seq) < SEQUENCE_LENGTH:
            seq = np.pad(seq, ((SEQUENCE_LENGTH - len(seq), 0), (0, 0)))
        return seq

    def run(self):
        print(f"Listening on topic: {KAFKA_TOPIC_IN}")
        for message in self.consumer:
            try:
                raw = message.value
                event = AccessEvent(**raw)
                features = engineer_features(event, self.baseline)

                iso_score = self.iso.score(features)
                session_seq = self._get_session_sequence(event.user_id, features)
                lstm_score = self.lstm.score(session_seq)
                graph_flag = self.graph.flag_violation(event)

                risk = compute_risk(event, iso_score, lstm_score, graph_flag, features)

                if risk.requires_alert:
                    self.producer.send(KAFKA_TOPIC_OUT, {
                        "event_id": risk.event_id,
                        "user_id": risk.user_id,
                        "patient_id": risk.patient_id,
                        "risk_tier": risk.risk_tier,
                        "combined_score": risk.combined_score,
                        "risk_factors": risk.risk_factors,
                    })
            except Exception as e:
                print(f"Error processing event: {e}")


# ---------------------------------------------------------------------------
# Batch training pipeline (SageMaker entry point)
# ---------------------------------------------------------------------------

def train(audit_log_df: pd.DataFrame, encounters_df: pd.DataFrame) -> tuple:
    baseline = UserBaselineTracker()
    feature_rows = []
    for _, row in audit_log_df.iterrows():
        event = AccessEvent(**{k: row[k] for k in AccessEvent.__dataclass_fields__})
        features = engineer_features(event, baseline)
        feature_rows.append(features)
    feature_df = pd.DataFrame(feature_rows)

    # Fit on presumed-normal access only (no known violations in training window)
    normal_df = feature_df[feature_df["in_care_relationship"] == 1]

    print("Training Isolation Forest...")
    iso = IsolationForestScorer()
    iso.fit(normal_df)

    print("Training LSTM Autoencoder...")
    lstm = LSTMAnomalyScorer()
    lstm.fit(normal_df, epochs=30)

    print("Building care relationship graph...")
    graph = CareRelationshipGraph()
    graph.build_from_encounters(encounters_df)

    return iso, lstm, graph


# ---------------------------------------------------------------------------
# FastAPI interface
# ---------------------------------------------------------------------------

app = FastAPI()

class EventRequest(BaseModel):
    event_id: str
    user_id: str
    role: str
    department: str
    patient_id: str
    record_type: str
    access_timestamp: str
    hour_of_day: int
    day_of_week: int
    session_record_count: int
    days_since_last_clinical_note: int
    in_care_relationship: bool
    location_id: str

@app.post("/score")
def score_event(req: EventRequest):
    """Score a single access event in real time (< 200ms target)."""
    return {"status": "requires_fitted_models", "event_id": req.event_id}


if __name__ == "__main__":
    np.random.seed(42)
    n = 5000

    audit_log = pd.DataFrame({
        "event_id": [f"EVT-{i:06d}" for i in range(n)],
        "user_id": np.random.choice([f"USR-{i:04d}" for i in range(50)], n),
        "role": np.random.choice(list(ROLE_MAP.keys()), n),
        "department": np.random.choice(["ICU", "Cardiology", "Billing", "Lab", "Radiology"], n),
        "patient_id": np.random.choice([f"PT-{i:05d}" for i in range(1000)], n),
        "record_type": np.random.choice(list(RECORD_TYPE_MAP.keys()), n),
        "access_timestamp": pd.date_range("2025-01-01", periods=n, freq="min").astype(str),
        "hour_of_day": np.random.randint(0, 24, n),
        "day_of_week": np.random.randint(0, 7, n),
        "session_record_count": np.random.poisson(5, n),
        "days_since_last_clinical_note": np.random.randint(0, 120, n),
        "in_care_relationship": np.random.binomial(1, 0.85, n).astype(bool),
        "location_id": np.random.choice([f"LOC-{i:02d}" for i in range(5)], n),
    })

    encounters = pd.DataFrame({
        "provider_id": np.random.choice([f"USR-{i:04d}" for i in range(50)], 3000),
        "patient_id": np.random.choice([f"PT-{i:05d}" for i in range(1000)], 3000),
        "encounter_date": pd.date_range("2024-10-01", periods=3000, freq="h").strftime("%Y-%m-%d"),
    })

    iso_model, lstm_model, graph = train(audit_log, encounters)
    print("\nAll models trained. Real-time pipeline requires Kafka broker.")
