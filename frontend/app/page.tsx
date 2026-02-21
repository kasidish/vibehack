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

export default function Home() {
  const [data, setData] = useState<ForecastPoint[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    fetch("http://127.0.0.1:8000/forecast")
      .then((res: Response) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((json: ForecastPoint[]) => {
        setData(Array.isArray(json) ? json : [])
      })
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err)
        setError(message)
        console.error(err)
      })
      .finally(() => setLoading(false))
  }, [])

  return (
    <div style={{ padding: 40 }}>
      <h1>AI Sales Forecast Dashboard</h1>

      {loading && <p>Loading forecast...</p>}
      {error && <p style={{ color: "red" }}>Error: {error}</p>}
      {!loading && !error && data.length === 0 && <p>No forecast data.</p>}
      {!loading && !error && data.length > 0 && (
        <ResponsiveContainer width="100%" height={400}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="ds" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="yhat" stroke="#8884d8" />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}