from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any

from ashby_core import (
    handle_feedback,
    handle_decay_cycle,
    handle_validate_mutation,
    handle_get_state
)

app = FastAPI(
    title="Ashby-Vira Core v2.0",
    description="The Deterministic Brain for Autonomous AI Systems",
    version="2.0.0"
)

# ============================================================================
# CORS MIDDLEWARE (FIXES NETWORK ERRORS FROM BASE44/LOCALHOST)
# ============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (Base44, Vercel, Localhost, etc.)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE)
    allow_headers=["*"],  # Allows all headers
)

# ============================================================================
# ROUTES
# ============================================================================

@app.get("/")
async def root():
    return {
        "system": "Ashby-Vira Core v2.0",
        "status": "ONLINE",
        "designed_by": "Ian Kubath",
        "ai_assisted_by": "Lumo (Proton)",
        "endpoints": {
            "GET /": "System Info",
            "GET /state": "Get Current Stability State",
            "POST /feedback": "Submit Feedback Event",
            "POST /decay": "Run Decay Cycle",
            "POST /validate": "Validate Mutation Graph"
        }
    }

@app.get("/state")
async def get_state():
    return handle_get_state()

@app.post("/feedback")
async def feedback(event: Dict[str, Any]):
    try:
        result = handle_feedback(event)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/decay")
async def decay():
    return handle_decay_cycle()

@app.post("/validate")
async def validate(mutation_graph: Dict[str, Any]):
    try:
        result = handle_validate_mutation(mutation_graph)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
