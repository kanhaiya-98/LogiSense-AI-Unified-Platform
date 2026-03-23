from __future__ import annotations
import uvicorn
from fastapi import FastAPI
import logging
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

from api import router as blockchain_router

app = FastAPI(title="Feature 9 Blockchain Audit Standalone")

@app.get("/")
async def root():
    return {"message": "Feature 9 Blockchain Audit Standalone", "status": "online"}

app.include_router(blockchain_router, prefix="/blockchain", tags=["blockchain"])

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8081)
