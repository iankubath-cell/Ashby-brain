from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

# Import the core logic functions
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

# --- Root Route (Fixes the "Not Found" error) ---
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

# --- State Route ---
@app.get("/state")
async def get_state():
    return handle_get_state()

# --- Feedback Route ---
@app.post("/feedback")
async def feedback(event: Dict[str, Any]):
    try:
        result = handle_feedback(event)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Decay Route ---
@app.post("/decay")
async def decay():
    return handle_decay_cycle()

# --- Validate Route ---
@app.post("/validate")
async def validate(mutation_graph: Dict[str, Any]):
    try:
        result = handle_validate_mutation(mutation_graph)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
