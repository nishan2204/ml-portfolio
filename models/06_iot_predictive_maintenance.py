"""
IoT Predictive Maintenance & Failure Explanation Agent
TCN and LSTM-Autoencoder on sensor telemetry for anomaly and failure prediction.
NLP pipeline on technician logs for root cause classification.
Agent layer explains failures in plain English with recommended interventions.
"""

import json
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, Trainer, TrainingArguments
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
from dataclasses import dataclass
from typing import Optional
import anthropic


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TCN_CHANNELS = [64, 128, 256, 128, 64]
TCN_KERNEL_SIZE = 3
LSTM_AE_HIDDEN = 128
SEQUENCE_LENGTH = 48          # 48 hours of hourly sensor readings
ANOMALY_THRESHOLD_PERCENTILE = 95
FAILURE_HORIZON_HOURS = 72    # predict failures within 72 hours
BATCH_SIZE = 64
EPOCHS = 40
LEARNING_RATE = 1e-3
NLP_MODEL = "distilbert-base-uncased"
FAULT_CLASSES = ["bearing_wear", "lubrication_failure", "electrical_fault",
                 "seal_degradation", "overheating", "vibration_imbalance", "unknown"]
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

SENSOR_COLS = [
    "temperature_c", "vibration_rms", "current_draw_a",
    "pressure_psi", "rpm", "oil_level_pct", "acoustic_db",
]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class AssetReading:
    asset_id: str
    timestamp: str
    sensor_data: dict           # {sensor_name: value}
    technician_log: Optional[str] = None
    known_failure: Optional[str] = None

@dataclass
class MaintenancePrediction:
    asset_id: str
    anomaly_score: float
    failure_probability: float
    predicted_failure_class: str
    time_to_failure_hours: Optional[float]
    explanation: str
    recommended_interventions: list[str]
    confidence: float


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class SensorDataset(Dataset):
    def __init__(self, sequences: np.ndarray, labels: Optional[np.ndarray] = None):
        self.X = torch.FloatTensor(sequences)
        self.y = torch.FloatTensor(labels) if labels is not None else None

    def __len__(self): return len(self.X)
    def __getitem__(self, idx):
        if self.y is not None:
            return self.X[idx], self.y[idx]
        return self.X[idx]


def build_sequences(df: pd.DataFrame, seq_len: int = SEQUENCE_LENGTH,
                    horizon: int = FAILURE_HORIZON_HOURS) -> tuple:
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(df[SENSOR_COLS].fillna(method="ffill").fillna(0))
    sequences, labels = [], []
    for i in range(seq_len, len(df) - horizon):
        sequences.append(X_scaled[i - seq_len:i])
        # Label: did a failure occur in the next `horizon` hours?
        labels.append(float(df["failure"].iloc[i:i + horizon].any()))
    return np.array(sequences), np.array(labels), scaler


# ---------------------------------------------------------------------------
# TCN (Temporal Convolutional Network) — failure prediction
# ---------------------------------------------------------------------------

class CausalConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, dilation: int):
        super().__init__()
        pad = (kernel_size - 1) * dilation
        self.conv = nn.Sequential(
            nn.Conv1d(in_ch, out_ch, kernel_size, dilation=dilation, padding=pad),
            nn.BatchNorm1d(out_ch),
            nn.GELU(),
            nn.Dropout(0.1),
        )
        self.residual = nn.Conv1d(in_ch, out_ch, 1) if in_ch != out_ch else nn.Identity()
        self.pad = pad

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.conv(x)[:, :, :x.size(2)]  # causal: trim future padding
        return out + self.residual(x)


class TCNFailurePredictor(nn.Module):
    def __init__(self, n_sensors: int = len(SENSOR_COLS),
                 channels: list = TCN_CHANNELS, kernel_size: int = TCN_KERNEL_SIZE):
        super().__init__()
        layers = []
        in_ch = n_sensors
        for i, out_ch in enumerate(channels):
            layers.append(CausalConvBlock(in_ch, out_ch, kernel_size, dilation=2**i))
            in_ch = out_ch
        self.tcn = nn.Sequential(*layers)
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool1d(1),
            nn.Flatten(),
            nn.Linear(channels[-1], 32),
            nn.GELU(),
            nn.Linear(32, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        # x: (batch, seq_len, features) -> (batch, features, seq_len) for Conv1d
        out = self.tcn(x.permute(0, 2, 1))
        return self.head(out).squeeze(1)


def train_tcn(sequences: np.ndarray, labels: np.ndarray) -> TCNFailurePredictor:
    dataset = SensorDataset(sequences, labels)
    n_train = int(0.85 * len(dataset))
    train_ds, val_ds = torch.utils.data.random_split(
        dataset, [n_train, len(dataset) - n_train]
    )
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE)

    model = TCNFailurePredictor()
    pos_weight = torch.tensor([((labels == 0).sum() / max((labels == 1).sum(), 1))])
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=LEARNING_RATE, epochs=EPOCHS, steps_per_epoch=len(train_loader)
    )

    for epoch in range(EPOCHS):
        model.train()
        for X_b, y_b in train_loader:
            optimizer.zero_grad()
            loss = criterion(model(X_b), y_b)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
        if (epoch + 1) % 10 == 0:
            model.eval()
            val_losses = [criterion(model(X_b), y_b).item() for X_b, y_b in val_loader]
            print(f"  Epoch {epoch+1}/{EPOCHS} — val loss: {np.mean(val_losses):.4f}")
    return model


# ---------------------------------------------------------------------------
# LSTM-Autoencoder — anomaly scoring
# ---------------------------------------------------------------------------

class LSTMAutoencoder(nn.Module):
    def __init__(self, n_features: int = len(SENSOR_COLS), hidden: int = LSTM_AE_HIDDEN):
        super().__init__()
        self.encoder = nn.LSTM(n_features, hidden, batch_first=True)
        self.decoder = nn.LSTM(hidden, hidden, batch_first=True)
        self.output = nn.Linear(hidden, n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h, c) = self.encoder(x)
        # Decode by repeating the bottleneck representation
        repeat = h.permute(1, 0, 2).repeat(1, x.size(1), 1)
        dec_out, _ = self.decoder(repeat, (h, c))
        return self.output(dec_out)


def train_autoencoder(normal_sequences: np.ndarray) -> LSTMAutoencoder:
    dataset = SensorDataset(normal_sequences)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)
    model = LSTMAutoencoder()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = nn.MSELoss()
    for epoch in range(EPOCHS):
        model.train()
        for (X_b,) in loader:
            optimizer.zero_grad()
            recon = model(X_b)
            loss = criterion(recon, X_b)
            loss.backward()
            optimizer.step()
    return model


def compute_anomaly_score(ae: LSTMAutoencoder, sequence: np.ndarray) -> float:
    ae.eval()
    with torch.no_grad():
        x = torch.FloatTensor(sequence).unsqueeze(0)
        recon = ae(x)
        return float(nn.MSELoss()(recon, x).item())


# ---------------------------------------------------------------------------
# NLP pipeline — root cause classification from technician logs
# ---------------------------------------------------------------------------

class FaultClassifier:
    def __init__(self, model_path: Optional[str] = None):
        self.tokenizer = AutoTokenizer.from_pretrained(NLP_MODEL)
        if model_path:
            self.model = AutoModelForSequenceClassification.from_pretrained(model_path)
        else:
            self.model = AutoModelForSequenceClassification.from_pretrained(
                NLP_MODEL, num_labels=len(FAULT_CLASSES)
            )
        self.model.eval()

    def predict(self, log_text: str) -> tuple[str, float]:
        inputs = self.tokenizer(log_text, return_tensors="pt",
                                truncation=True, max_length=256, padding=True)
        with torch.no_grad():
            logits = self.model(**inputs).logits
        probs = torch.softmax(logits, dim=-1).squeeze()
        idx = probs.argmax().item()
        return FAULT_CLASSES[idx], float(probs[idx])

    def fine_tune(self, log_df: pd.DataFrame, output_dir: str):
        """Fine-tune on labeled technician log dataset."""
        from datasets import Dataset as HFDataset

        def tokenize(batch):
            return self.tokenizer(batch["text"], truncation=True, max_length=256, padding="max_length")

        hf_ds = HFDataset.from_pandas(log_df[["text", "label"]])
        tokenized = hf_ds.map(tokenize, batched=True)

        args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=4,
            per_device_train_batch_size=16,
            learning_rate=2e-5,
            weight_decay=0.01,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
        )
        trainer = Trainer(model=self.model, args=args, train_dataset=tokenized)
        trainer.train()
        self.model.save_pretrained(output_dir)


# ---------------------------------------------------------------------------
# Explanation agent — Claude API
# ---------------------------------------------------------------------------

EXPLANATION_PROMPT = """You are a maintenance engineer AI assistant. Given sensor anomaly data
and a predicted fault classification, explain what is likely happening with the asset in plain English
and recommend specific maintenance interventions.

Be concise (3-4 sentences), specific, and actionable. Format as JSON:
{
  "explanation": "plain English explanation of what is happening",
  "interventions": ["intervention 1", "intervention 2", "intervention 3"],
  "urgency": "immediate|scheduled|monitor"
}"""

def generate_explanation(asset_id: str, anomaly_score: float, failure_prob: float,
                          fault_class: str, sensor_snapshot: dict) -> dict:
    client = anthropic.Anthropic()
    user_content = (
        f"Asset: {asset_id}\n"
        f"Anomaly score: {anomaly_score:.3f} (threshold: p95)\n"
        f"Failure probability (72h): {failure_prob:.1%}\n"
        f"Predicted fault class: {fault_class}\n"
        f"Current sensor readings: {json.dumps(sensor_snapshot, indent=2)}"
    )
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        system=EXPLANATION_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw = response.content[0].text.strip().lstrip("```json").rstrip("```").strip()
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Full inference pipeline
# ---------------------------------------------------------------------------

def predict_asset_health(asset_id: str, recent_readings: pd.DataFrame,
                          tcn_model: TCNFailurePredictor, ae_model: LSTMAutoencoder,
                          fault_classifier: FaultClassifier,
                          scaler: StandardScaler,
                          technician_log: Optional[str] = None) -> MaintenancePrediction:
    X = scaler.transform(recent_readings[SENSOR_COLS].fillna(method="ffill").fillna(0))
    seq = X[-SEQUENCE_LENGTH:][np.newaxis]

    anomaly_score = compute_anomaly_score(ae_model, seq)

    tcn_model.eval()
    with torch.no_grad():
        failure_prob = float(tcn_model(torch.FloatTensor(seq)).item())

    fault_class = "unknown"
    if technician_log:
        fault_class, _ = fault_classifier.predict(technician_log)

    sensor_snapshot = recent_readings[SENSOR_COLS].iloc[-1].to_dict()
    explanation_data = generate_explanation(
        asset_id, anomaly_score, failure_prob, fault_class, sensor_snapshot
    )

    return MaintenancePrediction(
        asset_id=asset_id,
        anomaly_score=anomaly_score,
        failure_probability=failure_prob,
        predicted_failure_class=fault_class,
        time_to_failure_hours=FAILURE_HORIZON_HOURS * (1 - failure_prob) if failure_prob > 0.5 else None,
        explanation=explanation_data.get("explanation", ""),
        recommended_interventions=explanation_data.get("interventions", []),
        confidence=min(1.0, failure_prob + 0.1),
    )


if __name__ == "__main__":
    np.random.seed(42)
    n_assets = 5
    n_timesteps = 200

    readings = pd.DataFrame({
        "temperature_c": np.random.normal(75, 5, n_timesteps),
        "vibration_rms": np.random.normal(0.8, 0.1, n_timesteps),
        "current_draw_a": np.random.normal(12, 1, n_timesteps),
        "pressure_psi": np.random.normal(90, 3, n_timesteps),
        "rpm": np.random.normal(1750, 50, n_timesteps),
        "oil_level_pct": np.random.uniform(60, 100, n_timesteps),
        "acoustic_db": np.random.normal(65, 3, n_timesteps),
        "failure": np.random.binomial(1, 0.05, n_timesteps),
    })

    sequences, labels, scaler = build_sequences(readings)
    print(f"Training sequences: {sequences.shape}, failure rate: {labels.mean():.2%}")
    print("TCN and Autoencoder training requires GPU — skipping in demo mode.")
    print("FaultClassifier requires labeled technician log dataset for fine-tuning.")
