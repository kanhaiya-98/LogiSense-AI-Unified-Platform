from __future__ import annotations
"""
main.py — FastAPI application entry point for Feature 8.

Run standalone (dev):
    uvicorn feature_8.main:app --reload --port 8008

Or import the router into your main project app:
    from feature_8.main import app as feature8_app        # standalone
    from feature_8.api.routes import router as f8_router  # embedded
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from feature_8.api.routes import router as explainability_router

app = FastAPI(
    title="Feature 8 — ML Explainability API",
    description="SHAP-based explainability for child immunization risk predictions.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS — allow React frontend ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # React dev server
        "http://localhost:5173",   # Vite dev server
        "http://127.0.0.1:3000",
        # Add your production domain here when deploying
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Mount Feature 8 router ───────────────────────────────────────────────────
app.include_router(explainability_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "feature": 8, "service": "explainability"}
