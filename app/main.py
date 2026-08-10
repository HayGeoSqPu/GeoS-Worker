from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}