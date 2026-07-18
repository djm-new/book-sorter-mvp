from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
HTML_PATH = APP_DIR / "books_sorter.html"
SECRET_PATH = "/books/4f8b2d7c"
DATA_DIR = Path(os.environ.get("BOOK_SORTER_DATA_DIR", "/data/book-sorter" if Path("/data").exists() else APP_DIR / ".data"))
DECISIONS_PATH = DATA_DIR / "decisions.json"
_decisions_lock = threading.Lock()

app = FastAPI(title="Book Sorter MVP")
app.mount("/sample-images", StaticFiles(directory=APP_DIR / "sample-images"), name="sample-images")
app.mount("/sample-crops", StaticFiles(directory=APP_DIR / "sample-crops"), name="sample-crops")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_decisions() -> dict[str, Any]:
    return {"version": 1, "updatedAt": None, "decisions": {}}


def _read_decisions_unlocked() -> dict[str, Any]:
    if not DECISIONS_PATH.exists():
        return _empty_decisions()
    try:
        data = json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_decisions()
    if not isinstance(data, dict):
        return _empty_decisions()
    decisions = data.get("decisions")
    if not isinstance(decisions, dict):
        decisions = {}
    cleaned: dict[str, Any] = {}
    for key, value in decisions.items():
        if isinstance(key, str) and isinstance(value, dict):
            cleaned[key] = value
    return {"version": 1, "updatedAt": data.get("updatedAt"), "decisions": cleaned}


def _write_decisions_unlocked(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA_DIR, delete=False) as tmp:
        tmp.write(payload)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(DECISIONS_PATH)


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    category = record.get("category")
    decision = record.get("decision")
    rotation = record.get("rotation", 0)
    if category not in {"coloring", "activity", "sticker"}:
        category = None
    if decision not in {"keep", "discard", None}:
        decision = None
    try:
        rotation = int(rotation) % 360
    except (TypeError, ValueError):
        rotation = 0
    return {
        "category": category,
        "decision": decision,
        "rotation": rotation,
        "updatedAt": _now_iso(),
    }


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url=SECRET_PATH, status_code=302)


@app.get("/health", include_in_schema=False)
def health():
    return {"ok": True}


@app.get(SECRET_PATH, include_in_schema=False)
def books_sorter_page():
    return HTMLResponse(HTML_PATH.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get("/books-sorter.html", include_in_schema=False)
def books_sorter_alias():
    return books_sorter_page()


@app.get("/api/decisions", include_in_schema=False)
def get_decisions():
    with _decisions_lock:
        return _read_decisions_unlocked()


@app.patch("/api/decisions/{book_hash}", include_in_schema=False)
def update_decision(book_hash: str, record: dict[str, Any]):
    if not book_hash or len(book_hash) > 128:
        raise HTTPException(status_code=400, detail="Invalid book hash")
    with _decisions_lock:
        data = _read_decisions_unlocked()
        data["decisions"][book_hash] = _clean_record(record)
        data["updatedAt"] = _now_iso()
        _write_decisions_unlocked(data)
        return {"ok": True, "hash": book_hash, "record": data["decisions"][book_hash], "updatedAt": data["updatedAt"]}


@app.delete("/api/decisions", include_in_schema=False)
def clear_decisions():
    with _decisions_lock:
        data = _empty_decisions()
        data["updatedAt"] = _now_iso()
        _write_decisions_unlocked(data)
        return {"ok": True, "updatedAt": data["updatedAt"], "decisions": {}}


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")
