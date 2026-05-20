from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware  # <--- ADD THIS IMPORT
from pydantic import BaseModel
from typing import Optional
import ashby_core

app = FastAPI()

# --- ADD THIS BLOCK TO ENABLE CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (use specific URLs in production)
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)
# -------------------------------------

class FeedbackEvent(BaseModel):
    type: str
    severity: str
    title: str
    message: str

@app.post("/api/feedback")
async def receive_feedback(event: FeedbackEvent):
    result = ashby_core.handle_feedback(event.dict())
    return result

@app.post("/api/decay")
async def run_decay():
    result = ashby_core.handle_decay_cycle()
    return result

@app.post("/api/validate-mutation")
async def validate_mutation(graph: dict):
    result = ashby_core.handle_validate_mutation(graph)
    return result

@app.get("/api/state")
async def get_state():
    return ashby_core.handle_get_state()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
