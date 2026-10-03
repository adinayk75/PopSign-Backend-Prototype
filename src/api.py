from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.embeddings import build_embedding_provider
from src.story_demo import generate_demo_story
from src.vector_matcher import LocalEvidenceSource, SupabaseEvidenceSource, VectorMatcher


ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
load_dotenv(ROOT / ".env")


class MatchRequest(BaseModel):
    phrase: str = Field(min_length=1, max_length=1000)
    target_word: str = Field(min_length=1, max_length=80)


class StoryRequest(BaseModel):
    prompt: str = Field(default="A child makes dinner for family and friends.", max_length=1000)
    difficulty: str = Field(default="Level A", max_length=40)


@lru_cache(maxsize=1)
def get_matcher() -> VectorMatcher:
    provider = build_embedding_provider()
    backend = os.getenv("POPSIGN_DATA_BACKEND", "local").casefold()
    if backend == "supabase":
        source = SupabaseEvidenceSource()
    elif backend == "local":
        source = LocalEvidenceSource()
    else:
        raise RuntimeError(f"Unknown POPSIGN_DATA_BACKEND: {backend}")
    return VectorMatcher(provider=provider, source=source)


def create_app() -> FastAPI:
    app = FastAPI(
        title="PopSign Vector Matching Prototype",
        version="0.2.0",
        description="Selects an ASL video meaning from phrase context.",
    )

    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/api/health")
    def health() -> dict:
        matcher = get_matcher()
        return {
            "status": "ok",
            "data_backend": os.getenv("POPSIGN_DATA_BACKEND", "local"),
            "embedding_model": matcher.provider.model_name,
            "embedding_version": matcher.provider.model_version,
            "dimensions": matcher.provider.dimensions,
        }

    @app.get("/api/catalog/words")
    def catalog_words() -> dict:
        source = get_matcher().source
        words = source.words() if isinstance(source, LocalEvidenceSource) else ["about", "can", "love"]
        return {"words": words}

    @app.post("/api/match")
    def match_phrase(request: MatchRequest) -> dict:
        try:
            return get_matcher().match(request.phrase, request.target_word).to_dict()
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/stories/demo")
    def create_story(request: StoryRequest) -> dict:
        return generate_demo_story(request.prompt, request.difficulty).to_dict()

    return app


app = create_app()
