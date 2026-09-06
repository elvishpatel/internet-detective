from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.database.db import initialize
from backend.api.health import router as health_router
from backend.api.investigations import router as investigation_router

app = FastAPI(title="Internet Detective", version="1.0.0")
origins = [x.strip() for x in settings.frontend_url.split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.include_router(health_router); app.include_router(investigation_router)

@app.on_event("startup")
def startup(): initialize()
