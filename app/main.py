"""Application FastAPI : API de chat + service du frontend."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.services.pipeline import run_pipeline

logger = logging.getLogger("meteorologue")

app = FastAPI(title="Météorologue IA", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"


class Message(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    include_data: bool = False


class ChatResponse(BaseModel):
    answer: str
    needs_location: bool = False
    data_block: dict | None = None


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "openai_configured": settings.openai_configured,
        "openai_model": settings.openai_model,
        "infoclimat_token_present": bool(settings.infoclimat_token),
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not settings.openai_configured:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY n'est pas définie. Renseignez la variable "
                "d'environnement puis relancez le serveur."
            ),
        )
    history = [{"role": m.role, "content": m.content} for m in req.messages]
    try:
        result = await run_pipeline(history)
    except Exception as exc:  # noqa: BLE001 - on renvoie une erreur lisible au client
        logger.exception("Erreur du pipeline météorologue")
        raise HTTPException(status_code=500, detail=f"Erreur interne : {exc!s}") from exc

    return ChatResponse(
        answer=result["answer"],
        needs_location=result.get("needs_location", False),
        data_block=result.get("data_block") if req.include_data else None,
    )


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
