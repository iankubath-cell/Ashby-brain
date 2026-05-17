from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
import ashby_core

app = FastAPI()

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