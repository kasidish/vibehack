from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from supabase import create_client
from dotenv import load_dotenv
import pandas as pd
from prophet import Prophet
import os
import io
import json
from openai import OpenAI
from pydantic import BaseModel

class ChatRequest(BaseModel):
    question: str

# Load .env first so OPENAI_API_KEY and others are available
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def _get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be set (e.g. in backend/.env)")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

# Lazy client so app starts even if .env is missing; fails on first /forecast if not configured
supabase = _get_supabase() if (SUPABASE_URL and SUPABASE_KEY) else None


def _records_to_grouped_df(records: list) -> pd.DataFrame:
    """Build Prophet-ready dataframe (ds, y) from list of dicts with sale_date and quantity."""
    df = pd.DataFrame(records)
    if "sale_date" not in df.columns or "quantity" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="Data must include 'sale_date' and 'quantity' (or columns that aggregate to them).",
        )
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    grouped = df.groupby("sale_date")["quantity"].sum().reset_index()
    grouped.columns = ["ds", "y"]
    if len(grouped) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need at least 2 distinct dates for forecasting.",
        )
    return grouped


def _format_forecast_result(out: pd.DataFrame) -> list:
    """Return list of {ds, yhat} with ds as YYYY-MM-DD string, yhat as float."""
    return [
        {
            "ds": row["ds"].strftime("%Y-%m-%d") if hasattr(row["ds"], "strftime") else str(row["ds"]),
            "yhat": round(float(row["yhat"]), 2),
        }
        for _, row in out.iterrows()
    ]


def _simple_forecast_fallback(grouped: pd.DataFrame, periods: int = 7) -> list:
    """Fallback when Prophet fails (e.g. CmdStan on Windows): linear extrapolation."""
    grouped = grouped.sort_values("ds").reset_index(drop=True)
    last_ds = grouped["ds"].iloc[-1]
    last_y = grouped["y"].iloc[-1]
    # Simple trend: average daily change over last 7 points (or all)
    n = min(7, len(grouped) - 1)
    if n >= 1:
        trend = (grouped["y"].iloc[-1] - grouped["y"].iloc[-1 - n]) / n
    else:
        trend = 0.0
    result = []
    for i in range(1, periods + 1):
        next_ds = last_ds + pd.Timedelta(days=i)
        next_y = last_y + trend * i
        result.append({"ds": next_ds, "yhat": max(0, next_y)})
    return _format_forecast_result(pd.DataFrame(result))


def _run_prophet_forecast(grouped: pd.DataFrame, periods: int = 7) -> list:
    """Run Prophet; return list of {ds, yhat}. On failure use simple fallback so API still works."""
    try:
        model = Prophet()
        model.fit(grouped)
        future = model.make_future_dataframe(periods=periods)
        pred = model.predict(future)
        out = pred[["ds", "yhat"]].tail(periods)
        return _format_forecast_result(out)
    except Exception:
        # Prophet/CmdStan often fails on Windows (e.g. error 3221225785). Use fallback.
        return _simple_forecast_fallback(grouped, periods)


@app.get("/")
def root():
    return {"message": "Backend is running"}


@app.get("/forecast")
def forecast_get():
    """GET /forecast: use data from Supabase."""
    if supabase is None:
        raise HTTPException(status_code=503, detail="SUPABASE_URL and SUPABASE_KEY not set. Add them to backend/.env")
    response = supabase.table("sales").select("*").execute()
    data = response.data
    if not data:
        raise HTTPException(status_code=400, detail="No sales data in database. POST CSV/JSON to /forecast instead.")
    df = pd.DataFrame(data)
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    grouped = df.groupby("sale_date")["quantity"].sum().reset_index()
    grouped.columns = ["ds", "y"]
    if len(grouped) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 distinct dates. Add more data or use POST /forecast with CSV/JSON.")
    forecast_result = _run_prophet_forecast(grouped)
    ai_result = _generate_ai_insight(forecast_result)

    return {
        "forecast": forecast_result,
        **ai_result
}


@app.post("/forecast")
async def forecast_post(request: Request, file: UploadFile | None = File(None)):
    """
    POST /forecast: send CSV or JSON body.
    - JSON: [{"sale_date": "2025-07-01", "product_name": "X", "quantity": 10}, ...]
    - CSV: sale_date,product_name,quantity,... (sale_date and quantity required)
    - Or upload a CSV file with multipart form 'file'.
    """
    raw: bytes
    content_type: str = (request.headers.get("content-type") or "").lower()

    if file and file.filename and file.filename.endswith(".csv"):
        raw = await file.read()
        try:
            df = pd.read_csv(io.BytesIO(raw))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")
    else:
        raw = await request.body()
        if not raw:
            raise HTTPException(status_code=400, detail="Send a JSON array or CSV in the request body.")
        if "application/json" in content_type or raw.strip().startswith(b"["):
            try:
                data = json.loads(raw.decode("utf-8"))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}")
            if not isinstance(data, list):
                raise HTTPException(status_code=400, detail="JSON body must be an array of rows.")
            df = pd.DataFrame(data)
        else:
            # Assume CSV
            try:
                df = pd.read_csv(io.BytesIO(raw))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Invalid CSV: {e}")

    # Normalize: allow sale_date + quantity, or sale_date + product_name + quantity (we aggregate)
    if "quantity" not in df.columns and "total_price" in df.columns:
        # generate_data has quantity; some CSVs might only have total_price
        df["quantity"] = df.get("total_price", 0) // 30  # fallback
    if "quantity" not in df.columns:
        raise HTTPException(status_code=400, detail="Data must include a 'quantity' (or 'total_price') column.")
    if "sale_date" not in df.columns:
        raise HTTPException(status_code=400, detail="Data must include a 'sale_date' column.")
    records = df.to_dict(orient="records")
    grouped = _records_to_grouped_df(records)
    forecast_result = _run_prophet_forecast(grouped)
    ai_result = _generate_ai_insight(forecast_result)

    return {
        "forecast": forecast_result,
        **ai_result
}

def _generate_ai_insight(forecast_data: list):
    if client is None:
        return {
            "insight": "AI key not configured. Add OPENAI_API_KEY to backend/.env and restart the backend.",
        }

    try:
        forecast_text = "\n".join(
            [f"{row['ds']} → {row['yhat']}" for row in forecast_data]
        )
        prompt = f"""
Here is a 7-day sales forecast:

{forecast_text}

1. Summarize the trend in simple business language.
2. Give one short recommendation to improve sales.
"""
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a business AI analyst."},
                {"role": "user", "content": prompt}
            ]
        )
        text = completion.choices[0].message.content or ""
        return {"insight": text}
    except Exception as e:
        err_str = str(e).lower()
        if "401" in err_str or "invalid_api_key" in err_str or "incorrect api key" in err_str:
            insight_msg = (
                "AI insight unavailable: invalid OpenAI API key. "
                "Get a valid key at https://platform.openai.com/account/api-keys and set OPENAI_API_KEY in backend/.env, then restart the backend. "
                "Forecast data is still shown below."
            )
        elif "429" in err_str or "quota" in err_str or "insufficient" in err_str:
            insight_msg = (
                "AI insight unavailable: your OpenAI account is out of quota or has no billing. "
                "Add a payment method at https://platform.openai.com/account/billing to enable AI insights. "
                "Forecast data is still shown below."
            )
        else:
            insight_msg = f"AI insight unavailable: {str(e)}. Forecast data is still shown below."
        return {"insight": insight_msg}

@app.post("/chat")
def chat_with_ai(payload: ChatRequest):
    if client is None:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured")

    # ดึง forecast ล่าสุดจาก Supabase
    response = supabase.table("sales").select("*").execute()
    data = response.data

    if not data:
        raise HTTPException(status_code=400, detail="No sales data")

    df = pd.DataFrame(data)
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    grouped = df.groupby("sale_date")["quantity"].sum().reset_index()
    grouped.columns = ["ds", "y"]

    forecast_result = _run_prophet_forecast(grouped)

    forecast_text = "\n".join(
        [f"{row['ds']} → {row['yhat']}" for row in forecast_result]
    )

    prompt = f"""
    Here is the 7-day sales forecast:
    {forecast_text}

    User question:
    {payload.question}

    Answer like a business AI analyst.
    """

    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a business forecasting AI."},
            {"role": "user", "content": prompt}
        ]
    )

    return {
        "answer": completion.choices[0].message.content
    }

@app.get("/")
def home():
    return {
        "app": "Vibehack AI Sales Intelligence",
        "status": "Running",
        "docs": "/docs"
    }