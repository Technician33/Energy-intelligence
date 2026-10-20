import requests
import pandas as pd
import math
import matplotlib.pyplot as plt
import numpy as np

weather_url = (
    "https://archive-api.open-meteo.com/v1/archive"
    "?latitude=50.85&longitude=4.35"
    "&start_date=2026-04-01&end_date=2026-10-15"
    "&hourly=shortwave_radiation,windspeed_10m"
    "&timezone=UTC"
)
w = requests.get(weather_url, timeout=15).json()

price_url = "https://api.energy-charts.info/price?bzn=BE&start=2026-04-01&end=2026-10-15"
p = requests.get(price_url, timeout=15).json()

weather_df = pd.DataFrame({
    "timestamp_hour": pd.to_datetime(w["hourly"]["time"], utc=True),
    "solar_w_m2": w["hourly"]["shortwave_radiation"],
    "wind_ms": w["hourly"]["windspeed_10m"]
})
print(weather_df.head(5))

p_df = pd.DataFrame({
    "timestamp": pd.to_datetime(p["unix_seconds"], unit="s", utc=True),
    "price_EUR_MWh": p["price"]
})



# EPEX prices are 15-min, weather is hourly — forward fill to 15-min
weather_df = weather_df.set_index("timestamp_hour")
weather_df = weather_df.resample("15min").ffill().reset_index()
weather_df = weather_df.rename(columns={"timestamp_hour": "timestamp"})


# Merge with price df
df = weather_df.merge(p_df, on="timestamp", how="left")

df["solar_w_m2"] = weather_df["solar_w_m2"].fillna(0)
df["wind_ms"] = weather_df["wind_ms"].fillna(weather_df["wind_ms"].median())

print(df.head(5))
