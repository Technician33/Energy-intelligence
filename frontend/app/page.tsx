"use client";

import { useEffect, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts";

const API = "http://localhost:8000";

type Signal = "cheap" | "normal" | "expensive";

interface CurrentPrice {
  timestamp: string;
  price_EUR_MWh: number;
  signal: Signal;
  P33: number;
  P67: number;
}

interface Interval {
  timestamp: string;
  price_EUR_MWh: number;
  signal: Signal;
}

const signalColor = {
  cheap: "text-green-400",
  normal: "text-yellow-400",
  expensive: "text-red-400",
};

const signalBg = {
  cheap: "bg-green-900",
  normal: "bg-yellow-900",
  expensive: "bg-red-900",
};

export default function Home() {
  const [current, setCurrent] = useState<CurrentPrice | null>(null);
  const [today, setToday] = useState<Interval[]>([]);

  useEffect(() => {
    fetch(`${API}/price/current`)
      .then((r) => r.json())
      .then(setCurrent);

    fetch(`${API}/price/today`)
      .then((r) => r.json())
      .then((d) => setToday(d.intervals));
  }, []);

  const chartData = today.map((i) => ({
    time: new Date(i.timestamp).toLocaleTimeString("en-BE", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Europe/Brussels",
    }),
    price: i.price_EUR_MWh,
  }));

  return (
    <main className="min-h-screen bg-gray-950 text-white p-8 max-w-6xl mx-auto">
      <h1 className="text-3xl font-bold mb-2">Belgian Energy Intelligence</h1>
      <p className="text-gray-400 mb-8">Live EPEX spot prices · 15-min resolution</p>

      {/* Current price card */}
      {current && (
        <div className={`rounded-xl p-6 mb-8 ${signalBg[current.signal]}`}>
          <p className="text-sm text-gray-300 mb-1">Current price</p>
          <p className={`text-5xl font-bold ${signalColor[current.signal]}`}>
            €{current.price_EUR_MWh.toFixed(2)}
            <span className="text-lg ml-2 font-normal">/MWh</span>
          </p>
          <p className={`text-xl mt-2 font-semibold uppercase ${signalColor[current.signal]}`}>
            {current.signal}
          </p>
          <p className="text-sm text-gray-400 mt-2">
            P33: €{current.P33} · P67: €{current.P67}
          </p>
        </div>
      )}

      {/* Price chart */}
      {today.length > 0 && (
        <div className="mb-8">
          <h2 className="text-xl font-semibold mb-4">Today's price curve</h2>
          <div className="bg-gray-900 rounded-xl p-4">
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={chartData}>
                <XAxis
                  dataKey="time"
                  tick={{ fill: "#9ca3af", fontSize: 11 }}
                  interval={15}
                />
                <YAxis
                    tick={{ fill: "#9ca3af", fontSize: 11 }}
                    tickFormatter={(v) => `€${v}`}
                    domain={["auto", "auto"]}
                />
                
                <Tooltip
                  contentStyle={{ backgroundColor: "#111827", border: "none" }}
                  labelStyle={{ color: "#9ca3af" }}
                  formatter={(v: number) => [`€${v.toFixed(2)}/MWh`, "Price"]}
                />
                {current && (
                  <>
                    <ReferenceLine y={current.P33} stroke="#4ade80" strokeDasharray="4 2" label={{ value: "P33", fill: "#4ade80", fontSize: 10 }} />
                    <ReferenceLine y={current.P67} stroke="#f87171" strokeDasharray="4 2" label={{ value: "P67", fill: "#f87171", fontSize: 10 }} />
                  </>
                )}
                <Line
                  type="monotone"
                  dataKey="price"
                  stroke="#60a5fa"
                  dot={false}
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Today's intervals grid */}
      <h2 className="text-xl font-semibold mb-4">Today's prices</h2>
      <div className="grid grid-cols-4 gap-2">
        {today.map((interval) => (
          <div
            key={interval.timestamp}
            className={`rounded p-2 text-xs ${signalBg[interval.signal]}`}
          >
            <p className="text-gray-300">
              {new Date(interval.timestamp).toLocaleTimeString("en-BE", {
                hour: "2-digit",
                minute: "2-digit",
                timeZone: "Europe/Brussels",
              })}
            </p>
            <p className={`font-bold ${signalColor[interval.signal]}`}>
              €{interval.price_EUR_MWh.toFixed(0)}
            </p>
          </div>
        ))}
      </div>
    </main>
  );
}