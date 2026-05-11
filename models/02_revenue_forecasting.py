"""
Revenue Forecasting & Denial Risk System
ARIMA + Bidirectional LSTM ensemble for denial volume prediction
and accounts receivable aging, with nightly automated retraining.
"""

import numpy as np
import pandas as pd
import boto3
import json
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller
from statsmodels.tsa.seasonal import seasonal_decompose
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_absolute_percentage_error
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ARIMA_ORDER = (2, 1, 2)
ARIMA_SEASONAL_ORDER = (1, 1, 1, 12)
LSTM_HIDDEN = 128
LSTM_LAYERS = 2
LSTM_DROPOUT = 0.2
LOOKBACK = 24       # months of history as input window
FORECAST_HORIZON = 6
BATCH_SIZE = 32
EPOCHS = 60
LEARNING_RATE = 3e-4
ENSEMBLE_WINDOW = 6  # rolling window to compute accuracy-based weights

S3_BUCKET = "revenue-forecasting-features"
SAGEMAKER_ROLE = "arn:aws:iam::ACCOUNT_ID:role/SageMakerExecutionRole"


# ---------------------------------------------------------------------------
# Data loading from Snowflake + S3 feature store
# ---------------------------------------------------------------------------

def load_training_data(snowflake_conn, feature_date: str) -> pd.DataFrame:
    query = f"""
        SELECT
            claim_date,
            payer_id,
            denial_volume,
            ar_aging_30,
            ar_aging_60,
            ar_aging_90,
            payer_mix_ratio,
            avg_claim_value,
            submission_lag_days
        FROM revenue.claims_features
        WHERE claim_date <= '{feature_date}'
        ORDER BY claim_date
    """
    df = pd.read_sql(query, snowflake_conn)
    df["claim_date"] = pd.to_datetime(df["claim_date"])
    df = df.set_index("claim_date").sort_index()
    return df


def load_feature_store(feature_date: str) -> pd.DataFrame:
    s3 = boto3.client("s3")
    key = f"features/{feature_date}/engineered_features.parquet"
    obj = s3.get_object(Bucket=S3_BUCKET, Key=key)
    return pd.read_parquet(obj["Body"])


# ---------------------------------------------------------------------------
# Stationarity check + ARIMA
# ---------------------------------------------------------------------------

def check_stationarity(series: pd.Series) -> dict:
    result = adfuller(series.dropna())
    return {
        "adf_statistic": result[0],
        "p_value": result[1],
        "is_stationary": result[1] < 0.05,
        "critical_values": result[4],
    }

def fit_arima(series: pd.Series) -> tuple:
    stat = check_stationarity(series)
    d = 0 if stat["is_stationary"] else 1
    order = (ARIMA_ORDER[0], d, ARIMA_ORDER[2])

    decomp = seasonal_decompose(series, model="additive", period=12, extrapolate_trend="freq")
    detrended = series - decomp.trend.fillna(method="bfill").fillna(method="ffill")

    model = ARIMA(detrended, order=order, seasonal_order=ARIMA_SEASONAL_ORDER,
                  enforce_stationarity=False)
    fitted = model.fit()

    forecast_obj = fitted.get_forecast(steps=FORECAST_HORIZON)
    trend_extension = decomp.trend.iloc[-1]
    point = forecast_obj.predicted_mean + trend_extension
    ci = forecast_obj.conf_int()
    return fitted, point, ci


# ---------------------------------------------------------------------------
# Bidirectional LSTM with attention
# ---------------------------------------------------------------------------

class TimeSeriesDataset(Dataset):
    def __init__(self, features: np.ndarray, targets: np.ndarray, lookback: int):
        self.X, self.y = [], []
        for i in range(lookback, len(features) - FORECAST_HORIZON + 1):
            self.X.append(features[i - lookback:i])
            self.y.append(targets[i:i + FORECAST_HORIZON])
        self.X = torch.FloatTensor(np.array(self.X))
        self.y = torch.FloatTensor(np.array(self.y))

    def __len__(self): return len(self.X)
    def __getitem__(self, idx): return self.X[idx], self.y[idx]


class AttentionLayer(nn.Module):
    def __init__(self, hidden_size: int):
        super().__init__()
        self.attn = nn.Linear(hidden_size * 2, 1)

    def forward(self, lstm_out: torch.Tensor) -> torch.Tensor:
        scores = torch.softmax(self.attn(lstm_out), dim=1)
        return (scores * lstm_out).sum(dim=1)


class BiLSTMForecaster(nn.Module):
    def __init__(self, input_size: int, hidden_size: int = LSTM_HIDDEN,
                 num_layers: int = LSTM_LAYERS, forecast_horizon: int = FORECAST_HORIZON):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True, bidirectional=True,
                            dropout=LSTM_DROPOUT)
        self.attention = AttentionLayer(hidden_size)
        self.fc = nn.Sequential(
            nn.Linear(hidden_size * 2, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, forecast_horizon),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)
        context = self.attention(lstm_out)
        return self.fc(context)


def train_lstm(df: pd.DataFrame, feature_cols: list[str],
               target_col: str = "denial_volume") -> tuple:
    scaler_X = StandardScaler()
    scaler_y = StandardScaler()

    X = scaler_X.fit_transform(df[feature_cols].values)
    y = scaler_y.fit_transform(df[[target_col]].values).ravel()

    dataset = TimeSeriesDataset(X, y, LOOKBACK)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

    model = BiLSTMForecaster(input_size=len(feature_cols))
    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
    criterion = nn.HuberLoss()

    model.train()
    for epoch in range(EPOCHS):
        epoch_loss = 0.0
        for X_batch, y_batch in loader:
            optimizer.zero_grad()
            pred = model(X_batch)
            loss = criterion(pred, y_batch)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step()
        if (epoch + 1) % 10 == 0:
            print(f"  Epoch {epoch+1}/{EPOCHS} — loss: {epoch_loss/len(loader):.4f}")

    return model, scaler_X, scaler_y


def predict_lstm(model: BiLSTMForecaster, recent_features: np.ndarray,
                 scaler_X: StandardScaler, scaler_y: StandardScaler) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        X = torch.FloatTensor(scaler_X.transform(recent_features)[-LOOKBACK:]).unsqueeze(0)
        pred_scaled = model(X).numpy().ravel()
    return scaler_y.inverse_transform(pred_scaled.reshape(-1, 1)).ravel()


# ---------------------------------------------------------------------------
# Walk-forward cross-validation + drift monitoring
# ---------------------------------------------------------------------------

def walk_forward_cv(df: pd.DataFrame, feature_cols: list[str],
                    n_folds: int = 6) -> dict:
    fold_size = len(df) // (n_folds + 1)
    arima_mapes, lstm_mapes = [], []

    for fold in range(n_folds):
        train_end = fold_size * (fold + 1)
        test_start = train_end
        test_end = test_start + FORECAST_HORIZON

        train_df = df.iloc[:train_end]
        test_df = df.iloc[test_start:test_end]
        if len(test_df) < FORECAST_HORIZON:
            break

        _, arima_pred, _ = fit_arima(train_df["denial_volume"])
        arima_mapes.append(mean_absolute_percentage_error(
            test_df["denial_volume"].values, arima_pred.values
        ))

        model, sx, sy = train_lstm(train_df, feature_cols)
        lstm_pred = predict_lstm(model, train_df[feature_cols].values, sx, sy)
        lstm_mapes.append(mean_absolute_percentage_error(
            test_df["denial_volume"].values[:FORECAST_HORIZON], lstm_pred
        ))

    return {
        "arima_mean_mape": float(np.mean(arima_mapes)),
        "lstm_mean_mape": float(np.mean(lstm_mapes)),
        "n_folds": n_folds,
    }


def compute_ensemble_weights(recent_errors: dict) -> dict:
    """Accuracy-based weighting over rolling window."""
    inv_arima = 1.0 / max(recent_errors["arima_mape"], 1e-6)
    inv_lstm = 1.0 / max(recent_errors["lstm_mape"], 1e-6)
    total = inv_arima + inv_lstm
    return {"arima": inv_arima / total, "lstm": inv_lstm / total}


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    arima_forecast: np.ndarray
    lstm_forecast: np.ndarray
    ensemble_forecast: np.ndarray
    ensemble_weights: dict
    cv_metrics: dict
    confidence_lower: np.ndarray
    confidence_upper: np.ndarray


def run_pipeline(df: pd.DataFrame, feature_cols: list[str]) -> ForecastResult:
    print("Step 1/4 — Walk-forward cross-validation...")
    cv_metrics = walk_forward_cv(df, feature_cols)
    print(f"  ARIMA MAPE: {cv_metrics['arima_mean_mape']:.3f}")
    print(f"  LSTM MAPE:  {cv_metrics['lstm_mean_mape']:.3f}")

    print("Step 2/4 — Fitting ARIMA...")
    _, arima_pred, arima_ci = fit_arima(df["denial_volume"])

    print("Step 3/4 — Training BiLSTM...")
    model, sx, sy = train_lstm(df, feature_cols)
    lstm_pred = predict_lstm(model, df[feature_cols].values, sx, sy)

    print("Step 4/4 — Computing ensemble...")
    weights = compute_ensemble_weights({
        "arima_mape": cv_metrics["arima_mean_mape"],
        "lstm_mape": cv_metrics["lstm_mean_mape"],
    })
    ensemble = (weights["arima"] * arima_pred.values +
                weights["lstm"] * lstm_pred)

    ci_width = (arima_ci.iloc[:, 1].values - arima_ci.iloc[:, 0].values) / 2
    return ForecastResult(
        arima_forecast=arima_pred.values,
        lstm_forecast=lstm_pred,
        ensemble_forecast=ensemble,
        ensemble_weights=weights,
        cv_metrics=cv_metrics,
        confidence_lower=ensemble - ci_width,
        confidence_upper=ensemble + ci_width,
    )


# ---------------------------------------------------------------------------
# SageMaker nightly retraining entry point
# ---------------------------------------------------------------------------

def sagemaker_train():
    """Entry point for AWS SageMaker training job (Lambda-triggered nightly)."""
    import os
    import joblib

    feature_date = os.environ.get("FEATURE_DATE", pd.Timestamp.today().strftime("%Y-%m-%d"))
    output_dir = os.environ.get("SM_MODEL_DIR", "/opt/ml/model")

    df = load_feature_store(feature_date)
    feature_cols = [c for c in df.columns if c != "denial_volume"]
    result = run_pipeline(df, feature_cols)

    joblib.dump(result, f"{output_dir}/forecast_result.pkl")
    with open(f"{output_dir}/metrics.json", "w") as f:
        json.dump(result.cv_metrics, f)
    print("Retraining complete.")


if __name__ == "__main__":
    np.random.seed(42)
    dates = pd.date_range("2021-01-01", periods=36, freq="MS")
    df = pd.DataFrame({
        "denial_volume": 200 + 40 * np.sin(np.linspace(0, 6 * np.pi, 36)) +
                         np.random.normal(0, 10, 36),
        "payer_mix_ratio": np.random.uniform(0.4, 0.9, 36),
        "avg_claim_value": np.random.uniform(800, 1400, 36),
        "submission_lag_days": np.random.uniform(2, 10, 36),
        "ar_aging_30": np.random.uniform(0.3, 0.6, 36),
        "ar_aging_60": np.random.uniform(0.1, 0.3, 36),
    }, index=dates)

    feature_cols = [c for c in df.columns if c != "denial_volume"]
    result = run_pipeline(df, feature_cols)
    print(f"\nEnsemble weights — ARIMA: {result.ensemble_weights['arima']:.2f}, "
          f"LSTM: {result.ensemble_weights['lstm']:.2f}")
    print(f"6-month forecast: {result.ensemble_forecast}")
