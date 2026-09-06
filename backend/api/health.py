from fastapi import APIRouter
router = APIRouter()

@router.get("/api/health")
def health(): return {"status": "ok", "service": "internet-detective", "ai": "optional"}
