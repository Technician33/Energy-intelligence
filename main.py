from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import pandas as pd
from datetime import datetime, timezone

app = FastAPI(title="Belgian Energy Intelligence API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"status": "ok", "message": "Belgian Energy Intelligence API"}

from datetime import datetime, timedelta, timezone

@app.get("/price/current")
def get_current_price():
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    
    url = f"https://api.energy-charts.info/price?bzn=BE&start={start}&end={end}"
    data = requests.get(url, timeout=10).json()
    
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(data["unix_seconds"], unit="s", utc=True),
        "price": data["price"]
    }).sort_values("timestamp").reset_index(drop=True)
    
    df["P33"] = df["price"].rolling(window=672).quantile(0.33)
    df["P67"] = df["price"].rolling(window=672).quantile(0.67)
    df = df.dropna()
    
    latest = df.iloc[-1]
    
    if latest["price"] <= latest["P33"]:
        signal = "cheap"
    elif latest["price"] >= latest["P67"]:
        signal = "expensive"
    else:
        signal = "normal"
    
    return {
        "timestamp": latest["timestamp"].isoformat(),
        "price_EUR_MWh": round(float(latest["price"]), 2),
        "signal": signal,
        "P33": round(float(latest["P33"]), 2),
        "P67": round(float(latest["P67"]), 2)
    }

@app.get("/price/today")
def get_today_prices():
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    
    url = f"https://api.energy-charts.info/price?bzn=BE&start={start}&end={end}"
    data = requests.get(url, timeout=10).json()
    
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(data["unix_seconds"], unit="s", utc=True),
        "price": data["price"]
    }).sort_values("timestamp").reset_index(drop=True)
    
    df["P33"] = df["price"].rolling(window=672).quantile(0.33)
    df["P67"] = df["price"].rolling(window=672).quantile(0.67)
    df = df.dropna()
    
    today = datetime.now(timezone.utc).date()
    today_df = df[df["timestamp"].dt.date == today]
    
    def signal(row):
        if row["price"] <= row["P33"]:
            return "cheap"
        elif row["price"] >= row["P67"]:
            return "expensive"
        else:
            return "normal"
    
    today_df = today_df.copy()
    today_df["signal"] = today_df.apply(signal, axis=1)
    
    return {
        "date": str(today),
        "intervals": [
            {
                "timestamp": row["timestamp"].isoformat(),
                "price_EUR_MWh": round(float(row["price"]), 2),
                "signal": row["signal"]
            }
            for _, row in today_df.iterrows()
        ]
    }

import joblib
import numpy as np

model = joblib.load("model.pkl")

@app.get("/price/forecast")
def get_forecast():
    end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    
    url = f"https://api.energy-charts.info/price?bzn=BE&start={start}&end={end}"
    data = requests.get(url, timeout=10).json()
    
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(data["unix_seconds"], unit="s", utc=True),
        "price": data["price"]
    }).sort_values("timestamp").reset_index(drop=True)
    
    df["P33"] = df["price"].rolling(window=672).quantile(0.33)
    df["P67"] = df["price"].rolling(window=672).quantile(0.67)
    df["price_lag_96"] = df["price"].shift(96)
    df["price_lag_192"] = df["price"].shift(192)
    df["rolling_mean"] = df["price"].rolling(96).mean()
    df["rolling_std"] = df["price"].rolling(96).std()
    df = df.dropna()

    # Weather for today
    weather_url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude=50.85&longitude=4.35"
        f"&start_date={start}&end_date={end}"
        "&hourly=shortwave_radiation,windspeed_10m&timezone=UTC"
    )
    w = requests.get(weather_url, timeout=15).json()
    weather_df = pd.DataFrame({
        "timestamp": pd.to_datetime(w["hourly"]["time"], utc=True),
        "solar_w_m2": w["hourly"]["shortwave_radiation"],
        "wind_ms": w["hourly"]["windspeed_10m"]
    })
    weather_df = weather_df.set_index("timestamp").resample("15min").ffill().reset_index()
    df = df.merge(weather_df, on="timestamp", how="left")
    df["solar_w_m2"] = df["solar_w_m2"].fillna(0)
    df["wind_ms"] = df["wind_ms"].fillna(df["wind_ms"].median())

    # Use last 96 rows (24 hours) as forecast input
    features = ["hour", "dow", "month", "price_lag_96",
                "price_lag_192", "rolling_mean", "rolling_std",
                "solar_w_m2", "wind_ms"]
    
    df["hour"] = df["timestamp"].dt.hour
    df["dow"] = df["timestamp"].dt.dayofweek
    df["month"] = df["timestamp"].dt.month
    df = df.dropna(subset=features)

    last_24h = df.tail(96)
    predictions = model.predict(last_24h[features])

    return {
        "forecast": [
            {
                "timestamp": row["timestamp"].isoformat(),
                "predicted_signal": pred
            }
            for (_, row), pred in zip(last_24h.iterrows(), predictions)
        ]
    }