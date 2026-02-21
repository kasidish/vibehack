from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from supabase import create_client
from dotenv import load_dotenv
import pandas as pd
from prophet import Prophet
import os
import io
import json

# Load .env from this file's directory so it works regardless of CWD
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
load_dotenv()  # also load from current working directory

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
    return _run_prophet_forecast(grouped)


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
    return _run_prophet_forecast(grouped)