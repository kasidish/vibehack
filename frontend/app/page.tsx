"use client"

import { useEffect, useState } from "react"
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer
} from "recharts"

type ForecastPoint = { ds: string; yhat: number }

function getApiBase(): string {
  if (typeof window === "undefined") return "http://localhost:8000"
  const env = process.env.NEXT_PUBLIC_API_URL
  if (env) return env.replace(/\/$/, "")
  return `${window.location.protocol}//${window.location.hostname}:8000`
}

export default function Home() {
  const [forecast, setForecast] = useState<ForecastPoint[]>([])
  const [insight, setInsight] = useState("")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [question, setQuestion] = useState("")
  const [answer, setAnswer] = useState("")

  useEffect(() => {
    const apiBase = getApiBase()
    setLoading(true)
    setError(null)
    fetch(`${apiBase}/forecast`)
      .then((res: Response) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((data: ForecastPoint[] | { forecast?: ForecastPoint[]; insight?: string }) => {
        if (Array.isArray(data)) {
          setForecast(data)
          setInsight("")
        } else {
          setForecast(Array.isArray(data?.forecast) ? data.forecast : [])
          setInsight(typeof data?.insight === "string" ? data.insight : "")
        }
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err)
        const isNetworkError = message === "Failed to fetch"
        setError(
          isNetworkError
            ? `Cannot reach backend at ${apiBase}. Start it with: cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`
            : message
        )
        console.error(err)
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div
      style={{
        padding: 40,
        minHeight: "100vh",
        background: "#1a1a2e",
        color: "#e8e8e8",
      }}
    >
      <h1 style={{ color: "#fff", marginBottom: 8 }}>AI Sales Forecast Dashboard</h1>

      {loading && <p style={{ color: "#b0b0b0" }}>Loading forecast...</p>}
      {error && (
        <p style={{ color: "#ff6b6b", background: "#2d1f1f", padding: 12, borderRadius: 8 }}>
          Error: {error}
        </p>
      )}

      {insight && (
        <>
          <h2 style={{ color: "#fff", marginTop: 24 }}>AI Insight</h2>
          <p
            style={{
              background: "#16213e",
              color: "#a8d4ff",
              padding: 20,
              borderRadius: 8,
              border: "1px solid #3a4a6b",
              lineHeight: 1.6,
            }}
          >
            {insight}
          </p>
        </>
      )}

      {!loading && !error && forecast.length === 0 && (
        <p style={{ color: "#b0b0b0" }}>No forecast data.</p>
      )}
      {!loading && !error && forecast.length > 0 && (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={forecast}>
            <CartesianGrid strokeDasharray="3 3" stroke="#3a4a6b" />
            <XAxis dataKey="ds" stroke="#a0a0a0" />
            <YAxis
              stroke="#a0a0a0"
              tickFormatter={(value) =>
                new Intl.NumberFormat("th-TH", {
                  style: "currency",
                  currency: "THB",
                }).format(value)
              }
            />
            <Tooltip
              contentStyle={{ background: "#16213e", border: "1px solid #3a4a6b", color: "#e8e8e8" }}
            />
            <Line type="monotone" dataKey="yhat" name="Baht" stroke="#7c9ce0" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      )}

      <h2 style={{ marginTop: 40, color: "#fff" }}>Ask AI</h2>
      <input
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask about sales..."
        style={{
          padding: 10,
          width: "60%",
          background: "#16213e",
          color: "#e8e8e8",
          border: "1px solid #3a4a6b",
          borderRadius: 6,
        }}
      />
      <button
        onClick={async () => {
          const apiBase = getApiBase()
          try {
            const res = await fetch(`${apiBase}/chat`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ question })
            })
            const data = (await res.json()) as { answer?: string }
            setAnswer(data?.answer ?? (res.ok ? "" : "Request failed."))
          } catch (e) {
            setAnswer(
              `Failed to reach backend at ${apiBase}. Start it with: cd backend && python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000`
            )
          }
        }}
        style={{
          marginLeft: 10,
          padding: "10px 20px",
          background: "#3a4a6b",
          color: "#fff",
          border: "none",
          borderRadius: 6,
          cursor: "pointer",
        }}
      >
        Ask
      </button>
      {answer && (
        <p
          style={{
            marginTop: 20,
            background: "#16213e",
            color: "#a8d4ff",
            padding: 20,
            borderRadius: 8,
            border: "1px solid #3a4a6b",
            lineHeight: 1.6,
          }}
        >
          {answer}
        </p>
      )}
    </div>
  )
}