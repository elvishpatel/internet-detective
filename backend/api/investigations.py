import asyncio
import re
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.database import db
from backend.investigator import run, challenge

router = APIRouter()
class InvestigationInput(BaseModel):
    claim: str = Field(min_length=8, max_length=600)
    mode: str = Field(default="standard", pattern="^(standard|deep)$")

@router.post("/api/investigate")
async def create(payload: InvestigationInput):
    claim = " ".join(payload.claim.split())
    if not re.search(r"[A-Za-z0-9]", claim): raise HTTPException(422, "Enter a meaningful claim.")
    case_id = "CASE-" + uuid.uuid4().hex[:8].upper()
    db.create_investigation(case_id, claim, payload.mode)
    asyncio.create_task(run(case_id, claim, payload.mode))
    return {"investigation_id": case_id, "status": "queued"}

@router.get("/api/investigate/{case_id}")
def get(case_id: str):
    item = db.get_case(case_id)
    if not item: raise HTTPException(404, "Case not found")
    return item

@router.get("/api/investigate/{case_id}/status")
def status(case_id: str):
    item = db.get_case(case_id)
    if not item: raise HTTPException(404, "Case not found")
    return {k: item.get(k) for k in ("id", "status", "stage", "error", "created_at", "updated_at")}

@router.get("/api/investigate/{case_id}/evidence")
def evidence(case_id: str): return _part(case_id, "evidence")
@router.get("/api/investigate/{case_id}/timeline")
def timeline(case_id: str): return _part(case_id, "timeline")
@router.get("/api/investigate/{case_id}/graph")
def graph(case_id: str): return _part(case_id, "graph")

def _part(case_id, key):
    item = db.get_case(case_id)
    if not item: raise HTTPException(404, "Case not found")
    if not item.get("result"): return {key: []}
    return {key: item["result"].get(key, [])}

@router.post("/api/investigate/{case_id}/challenge")
async def adversarial(case_id: str):
    result = await challenge(case_id)
    if not result: raise HTTPException(409, "A completed case is required before it can be challenged.")
    return result["challenge"]
