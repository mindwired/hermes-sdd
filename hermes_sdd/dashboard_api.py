"""Shared FastAPI backend for Hermes Dashboard and Desktop adapters."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .core import SDDService
from .doctor import run_doctor
from .storage import read_jsonl, resolve_root
from .version import PLUGIN_ID, __version__


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=f"ValueError: {exc}")
    return HTTPException(status_code=500, detail="Internal server error")


def create_router(service: SDDService | None = None) -> APIRouter:
    active_service = service or SDDService()
    api = APIRouter()

    @api.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "plugin": PLUGIN_ID, "version": __version__}

    @api.get("/doctor")
    async def doctor(root: str | None = None) -> dict[str, Any]:
        return run_doctor(root)

    @api.get("/sources")
    async def list_sources() -> dict[str, Any]:
        return active_service.execute("list_sources")

    @api.post("/sources")
    async def register_source(body: dict[str, Any]) -> dict[str, Any]:
        try:
            return active_service.execute("register_source", root=body.get("path"), payload=body)
        except Exception as exc:
            raise _error(exc) from exc

    @api.delete("/sources/{source_id}")
    async def remove_source(source_id: str) -> dict[str, Any]:
        try:
            return active_service.execute("remove_source", target=source_id)
        except Exception as exc:
            raise _error(exc) from exc

    @api.get("/snapshot")
    async def snapshot(root: str = Query(...)) -> dict[str, Any]:
        try:
            return active_service.snapshot(root)
        except Exception as exc:
            raise _error(exc) from exc

    @api.get("/events")
    async def events(root: str = Query(...), limit: int = 30) -> dict[str, Any]:
        try:
            project_root = resolve_root(root)
            rows = read_jsonl(project_root / ".sdd" / "events.jsonl", limit=max(1, min(limit, 200)))
            return {"ok": True, "events": rows}
        except Exception as exc:
            raise _error(exc) from exc

    @api.get("/context")
    async def context(
        root: str = Query(...),
        task_id: str | None = None,
        milestone_id: str | None = None,
        checkpoint_id: str | None = None,
        budget_tokens: int = 12000,
    ) -> dict[str, Any]:
        try:
            return active_service.execute(
                "context_pack",
                root=root,
                target=task_id,
                payload={"milestone_id": milestone_id, "checkpoint_id": checkpoint_id},
                options={"budget_tokens": budget_tokens},
            )
        except Exception as exc:
            raise _error(exc) from exc

    @api.post("/operation")
    async def operation(body: dict[str, Any]) -> dict[str, Any]:
        try:
            return active_service.execute(
                str(body.get("operation") or ""),
                root=body.get("root"),
                target=body.get("target"),
                payload=body.get("payload") or {},
                options=body.get("options") or {},
            )
        except Exception as exc:
            raise _error(exc) from exc

    return api


router = create_router()
