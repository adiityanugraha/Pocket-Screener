from pathlib import Path
import json

import numpy as np
import onnx
import onnxruntime as ort
import pandas as pd
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.pipeline import Pipeline


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "historical_daily.csv"
MODEL_PATH = ROOT / "public" / "model.onnx"
METRICS_PATH = ROOT / "public" / "model_metrics.json"

FEATURE_COLUMNS = [
    "return_1d",
    "return_5d",
    "ma5_ratio",
    "ma20_ratio",
    "volume_ratio_20",
    "value_log",
    "rsi_14",
    "macd",
    "macd_signal",
    "macd_histogram",
    "bb_position",
    "atr_pct",
    "vwap_ratio",
]


def main():
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    features = build_dataset(df)

    split_date = features["date"].quantile(0.8)
    train = features[features["date"] <= split_date]
    # Purge gap: target baris train terakhir tidak bocor ke periode test.
    test = features[features["date"] > split_date + pd.Timedelta(days=7)]

    x_train = train[FEATURE_COLUMNS].astype(np.float32)
    y_train = train["target"].astype(int)
    x_test = test[FEATURE_COLUMNS].astype(np.float32)
    y_test = test["target"].astype(int)

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=250,
                    min_samples_leaf=8,
                    class_weight="balanced_subsample",
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ],
    )
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    baseline_accuracy = float(max(y_test.mean(), 1 - y_test.mean()))
    metrics = {
        "generatedAt": pd.Timestamp.now("UTC").isoformat(),
        "model": "RandomForestClassifier",
        "target": "next_day_close_return_positive",
        "features": FEATURE_COLUMNS,
        "trainRows": int(len(train)),
        "testRows": int(len(test)),
        "periodStart": features["date"].min().date().isoformat(),
        "periodEnd": features["date"].max().date().isoformat(),
        "splitDate": pd.Timestamp(split_date).date().isoformat(),
        "baselineAccuracy": baseline_accuracy,
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(precision_score(y_test, predictions, zero_division=0)),
        "recall": float(recall_score(y_test, predictions, zero_division=0)),
    }

    initial_type = [("float_input", FloatTensorType([None, len(FEATURE_COLUMNS)]))]
    classifier = model.named_steps["classifier"]
    onnx_model = convert_sklearn(
        model,
        initial_types=initial_type,
        target_opset=15,
        options={id(classifier): {"zipmap": False}},
    )
    onnx.checker.check_model(onnx_model)
    MODEL_PATH.write_bytes(onnx_model.SerializeToString())

    verify_onnx_model(model, MODEL_PATH, x_test.head(5).to_numpy(dtype=np.float32))
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(metrics, indent=2))
    print(f"ONNX saved: {MODEL_PATH.relative_to(ROOT)}")
    print(f"Metrics saved: {METRICS_PATH.relative_to(ROOT)}")


def build_dataset(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["symbol", "date"]).copy()
    engineered = pd.concat(
        [add_features(group) for _, group in df.groupby("symbol", sort=False)],
        ignore_index=True,
    )
    # Target 1-hari dipertahankan: diuji vs horizon 5-hari (Jul 2026), lift
    # precision top-decile 1d (+5.0pp) > 5d (+1.5pp) di test set yang sama.
    engineered["next_close"] = engineered.groupby("symbol")["close"].shift(-1)
    engineered["target"] = (engineered["next_close"] > engineered["close"]).astype(int)
    engineered = engineered.dropna(subset=FEATURE_COLUMNS + ["target", "next_close"])

    return engineered.reset_index(drop=True)


def add_features(group: pd.DataFrame) -> pd.DataFrame:
    group = group.copy()
    close = group["close"]
    high = group["high"]
    low = group["low"]
    volume = group["volume"]

    group["return_1d"] = close.pct_change()
    group["return_5d"] = close.pct_change(5)
    group["ma5"] = close.rolling(5).mean()
    group["ma20"] = close.rolling(20).mean()
    group["ma5_ratio"] = close / group["ma5"] - 1
    group["ma20_ratio"] = close / group["ma20"] - 1
    group["volume_ratio_20"] = volume / volume.rolling(20).mean()
    group["value_log"] = np.log1p(close * volume)
    group["rsi_14"] = rsi(close, 14)

    macd_line, signal_line, histogram = macd(close)
    group["macd"] = macd_line
    group["macd_signal"] = signal_line
    group["macd_histogram"] = histogram

    middle = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    upper = middle + 2 * std
    lower = middle - 2 * std
    group["bb_position"] = (close - lower) / (upper - lower)

    true_range = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)
    group["atr_pct"] = true_range.ewm(alpha=1 / 14, adjust=False).mean() / close

    # VWAP window 60 bar - match serving: backend inference memuat LOOKBACK_BARS=60
    # bar lalu menghitung VWAP kumulatif atas 60 bar itu. VWAP kumulatif dari awal
    # dataset akan non-stasioner dan tidak konsisten dengan serving.
    typical_price = (high + low + close) / 3
    rolling_tpv = (typical_price * volume).rolling(60).sum()
    rolling_volume = volume.rolling(60).sum()
    group["vwap_ratio"] = close / (rolling_tpv / rolling_volume) - 1

    return group


def rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    average_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    average_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    value = 100 - 100 / (1 + relative_strength)

    return value.fillna(100).where(average_gain != 0, 0)


def macd(close: pd.Series):
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


def verify_onnx_model(sk_model: Pipeline, model_path: Path, sample: np.ndarray):
    """Pastikan output ONNX == sklearn. skl2onnx 1.20 + sklearn 1.9 pernah
    menghasilkan probabilitas [-p, p] dan label salah tanpa error apa pun -
    pakai stack pinned di requirements-train.txt."""
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: sample})

    if len(outputs) < 2:
        raise RuntimeError("Expected ONNX classifier to return label and probability outputs")

    expected_proba = sk_model.predict_proba(sample)
    onnx_proba = np.asarray(outputs[1])
    if not np.allclose(onnx_proba, expected_proba, atol=1e-4):
        raise RuntimeError(
            f"ONNX probabilities menyimpang dari sklearn:\n"
            f"onnx    = {onnx_proba.tolist()}\n"
            f"sklearn = {expected_proba.tolist()}"
        )
    if not np.array_equal(np.asarray(outputs[0]).reshape(-1), sk_model.predict(sample)):
        raise RuntimeError("ONNX labels menyimpang dari sklearn")


if __name__ == "__main__":
    main()
