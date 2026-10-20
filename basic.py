import os
import numpy as np
import requests
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report

# ── 1. EPEX prices (cached) ────────────────────────────────────────────────
CACHE_FILE = "electricity_prices.csv"
if os.path.exists(CACHE_FILE):
    df = pd.read_csv(CACHE_FILE)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    print("EPEX loaded from cache")
else:
    url = "https://api.energy-charts.info/price?bzn=BE&start=2026-04-01&end=2026-10-15"
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    data = response.json()
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(data["unix_seconds"], unit="s", utc=True),
        "price_EUR_MWh": data["price"]
    })
    df.to_csv(CACHE_FILE, index=False)
    print("EPEX fetched and cached")

df = df.sort_values("timestamp").reset_index(drop=True)

# ── 2. Weather (cached) ────────────────────────────────────────────────────
WEATHER_CACHE = "weather.csv"
if os.path.exists(WEATHER_CACHE):
    weather_df = pd.read_csv(WEATHER_CACHE)
    weather_df["timestamp"] = pd.to_datetime(weather_df["timestamp"], utc=True)
    print("Weather loaded from cache")
else:
    weather_url = (
        "https://archive-api.open-meteo.com/v1/archive"
        "?latitude=50.85&longitude=4.35"
        "&start_date=2026-04-01&end_date=2026-10-15"
        "&hourly=shortwave_radiation,windspeed_10m"
        "&timezone=UTC"
    )
    w = requests.get(weather_url, timeout=30).json()
    weather_df = pd.DataFrame({
        "timestamp": pd.to_datetime(w["hourly"]["time"], utc=True),
        "solar_w_m2": w["hourly"]["shortwave_radiation"],
        "wind_ms": w["hourly"]["windspeed_10m"]
    })
    weather_df = weather_df.set_index("timestamp").resample("15min").ffill().reset_index()
    weather_df.to_csv(WEATHER_CACHE, index=False)
    print("Weather fetched and cached")

df = df.merge(weather_df, on="timestamp", how="left")
df["solar_w_m2"] = df["solar_w_m2"].fillna(0)
df["wind_ms"] = df["wind_ms"].fillna(df["wind_ms"].median())

# ── 3. Rolling thresholds (no lookahead) ───────────────────────────────────
df["P33"] = df["price_EUR_MWh"].rolling(window=672).quantile(0.33)
df["P67"] = df["price_EUR_MWh"].rolling(window=672).quantile(0.67)
df = df.dropna(subset=["P33", "P67"]).reset_index(drop=True)

# ── 4. Signal label ────────────────────────────────────────────────────────
def classify(row):
    if row["price_EUR_MWh"] <= row["P33"]:
        return "cheap"
    elif row["price_EUR_MWh"] >= row["P67"]:
        return "expensive"
    else:
        return "normal"

df["signal"] = df.apply(classify, axis=1)
print("Signal distribution:\n", df["signal"].value_counts())

# ── 5. Feature engineering ─────────────────────────────────────────────────
df["hour"] = df["timestamp"].dt.hour
df["dow"] = df["timestamp"].dt.dayofweek
df["month"] = df["timestamp"].dt.month
df["price_lag_96"] = df["price_EUR_MWh"].shift(96)
df["price_lag_192"] = df["price_EUR_MWh"].shift(192)
df["rolling_mean"] = df["price_EUR_MWh"].rolling(96).mean()
df["rolling_std"] = df["price_EUR_MWh"].rolling(96).std()
df = df.dropna().reset_index(drop=True)
df["signal"] = df.apply(classify, axis=1)

# ── 6. Train classifier ────────────────────────────────────────────────────
features = ["hour", "dow", "month", "price_lag_96",
            "price_lag_192", "rolling_mean", "rolling_std",
            "solar_w_m2", "wind_ms"]

X = df[features]
y = df["signal"]

tscv = TimeSeriesSplit(n_splits=5)
for train_idx, test_idx in tscv.split(X):
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

model = RandomForestClassifier(n_estimators=100, random_state=42)
model.fit(X_train, y_train)

import joblib
joblib.dump(model, "model.pkl")
print("Model saved to model.pkl")

y_pred = model.predict(X_test)
print("\nClassifier performance:")
print(classification_report(y_test, y_pred))

importances = pd.Series(model.feature_importances_, index=features).sort_values(ascending=False)
print("\nFeature importances:")
print(importances)

# ── 7. Compare ML vs rolling window ───────────────────────────────────────
def run_simulation(signals, prices_df, label):
    CAPACITY_KWH = 10.0
    MIN_SOC = 0.15
    MAX_SOC = 0.95
    CHARGE_POWER_KW = 3.3
    INTERVAL_H = 0.25
    soc = 0.5
    results = []

    for sig, price, ts in zip(signals, prices_df["price_EUR_MWh"], prices_df["timestamp"]):
        if sig == "cheap" and soc < MAX_SOC:
            delta = min(CHARGE_POWER_KW * INTERVAL_H, (MAX_SOC - soc) * CAPACITY_KWH)
            soc += delta / CAPACITY_KWH
            action = "charge"
        elif sig == "expensive" and soc > MIN_SOC:
            delta = min(CHARGE_POWER_KW * INTERVAL_H, (soc - MIN_SOC) * CAPACITY_KWH)
            soc -= delta / CAPACITY_KWH
            action = "discharge"
        else:
            action = "idle"
        results.append({"timestamp": ts, "price": price,
                        "signal": sig, "action": action, "soc": round(soc, 3)})

    results_df = pd.DataFrame(results)
    results_df["revenue"] = results_df.apply(
        lambda row: (CHARGE_POWER_KW * INTERVAL_H) * (
            -row["price"] / 1000 if row["action"] == "charge"
            else row["price"] / 1000 if row["action"] == "discharge"
            else 0), axis=1)
    print(f"\n{label}: €{results_df['revenue'].sum():.2f}")
    return results_df

test_df = df.iloc[test_idx].reset_index(drop=True)
ml_results = run_simulation(list(y_pred), test_df, "ML strategy")
rolling_results = run_simulation(list(test_df["signal"]), test_df, "Rolling window strategy")

ml_daily = ml_results.groupby(ml_results["timestamp"].dt.date)["revenue"].sum()
rolling_daily = rolling_results.groupby(rolling_results["timestamp"].dt.date)["revenue"].sum()

comparison = pd.DataFrame({"ML": ml_daily, "Rolling window": rolling_daily})
comparison.plot(figsize=(14, 4), title="ML vs Rolling window — daily revenue (€)")
plt.tight_layout()
plt.savefig("comparison.png")
plt.show()