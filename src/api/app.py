"""FastAPI main application initialization for the Enterprise HR Virtual Assistant.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import router

app = FastAPI(
    title="Altostrat Enterprise HR Virtual Assistant",
    description="Agentic solution for enterprise HR policies, WorkWeek HCM, and ServiceImmediately ITSM support.",
    version="1.0.0"
)

# CORS middleware for corporate intranet portal & local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
