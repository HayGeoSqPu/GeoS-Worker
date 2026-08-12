from fastapi import FastAPI
import uvicorn
from app.core.config import settings
from app.api.v1.router import router

app = FastAPI(title=settings.PROJECT_NAME)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok"}


app.include_router(router, prefix=settings.API_V1_STR, tags=["cron"])


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)