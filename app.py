from __future__ import annotations

import html
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
CONTACT_SHEET_HTML_PATH = APP_DIR / "contact_sheet.html"
SECRET_PATH = "/books/4f8b2d7c"
ADMIN_ACTIVITY_PATH = "/admin/activity/4f8b2d7c"
CONTACT_SHEET_PATH = "/books/contact-sheet/4f8b2d7c"
DATA_DIR = Path(os.environ.get("BOOK_SORTER_DATA_DIR", "/data/book-sorter" if Path("/data").exists() else APP_DIR / ".data"))
DECISIONS_PATH = DATA_DIR / "decisions.json"
ACTIVITY_PATH = DATA_DIR / "activity.json"
_decisions_lock = threading.Lock()
_activity_lock = threading.Lock()

app = FastAPI(title="Book Sorter MVP")
app.mount("/sample-images", StaticFiles(directory=APP_DIR / "sample-images"), name="sample-images")
app.mount("/sample-crops", StaticFiles(directory=APP_DIR / "sample-crops"), name="sample-crops")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json_unlocked(path: Path, data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=DATA_DIR, delete=False) as tmp:
        tmp.write(payload)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


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
    _write_json_unlocked(DECISIONS_PATH, data)


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


def _empty_activity() -> dict[str, Any]:
    return {"version": 1, "updatedAt": None, "sessions": {}}


def _read_activity_unlocked() -> dict[str, Any]:
    if not ACTIVITY_PATH.exists():
        return _empty_activity()
    try:
        data = json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_activity()
    if not isinstance(data, dict):
        return _empty_activity()
    sessions = data.get("sessions")
    if not isinstance(sessions, dict):
        sessions = {}
    cleaned: dict[str, Any] = {}
    for key, value in sessions.items():
        if isinstance(key, str) and isinstance(value, dict):
            cleaned[key] = value
    return {"version": 1, "updatedAt": data.get("updatedAt"), "sessions": cleaned}


def _session_label(payload: dict[str, Any]) -> str:
    label = str(payload.get("deviceLabel") or payload.get("label") or "Unknown device").strip()
    return label[:120] or "Unknown device"


def _session_id(payload: dict[str, Any]) -> str:
    session_id = str(payload.get("sessionId") or "").strip()
    if not session_id or len(session_id) > 128:
        raise HTTPException(status_code=400, detail="Invalid session id")
    return session_id


def _upsert_session_unlocked(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    now = _now_iso()
    data = _read_activity_unlocked()
    session_id = _session_id(payload)
    sessions = data["sessions"]
    session = sessions.get(session_id) or {
        "sessionId": session_id,
        "firstSeen": now,
        "lastSeen": now,
        "deviceLabel": _session_label(payload),
        "userAgent": str(payload.get("userAgent") or "")[:300],
        "pageLoads": 0,
        "activeSeconds": 0,
        "actions": {"keep": 0, "discard": 0, "clear": 0, "category": 0, "rotation": 0, "other": 0},
        "lastAction": None,
    }
    session["lastSeen"] = now
    session["deviceLabel"] = _session_label(payload)
    if payload.get("userAgent"):
        session["userAgent"] = str(payload.get("userAgent"))[:300]
    if payload.get("pageLoad"):
        session["pageLoads"] = int(session.get("pageLoads") or 0) + 1
    try:
        active_delta = max(0, min(120, int(payload.get("activeSecondsDelta") or 0)))
    except (TypeError, ValueError):
        active_delta = 0
    session["activeSeconds"] = int(session.get("activeSeconds") or 0) + active_delta
    sessions[session_id] = session
    data["updatedAt"] = now
    return data, session


def _activity_admin_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Book Sorter Activity</title>
  <style>
    body { margin: 0; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #070b16; color: #f8fafc; }
    main { width: min(980px, 100%); margin: 0 auto; padding: 20px 14px 40px; }
    h1 { margin: 0 0 8px; letter-spacing: -0.04em; }
    .muted { color: rgba(226, 232, 240, .72); }
    .grid { display: grid; gap: 10px; margin-top: 16px; }
    .card { border: 1px solid rgba(255,255,255,.12); border-radius: 18px; padding: 14px; background: rgba(15, 23, 42, .82); box-shadow: 0 18px 35px rgba(0,0,0,.28); }
    .row { display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .active { color: #22c55e; font-weight: 800; }
    .inactive { color: #f59e0b; font-weight: 800; }
    code { color: #93c5fd; word-break: break-all; }
  </style>
</head>
<body>
<main>
  <h1>Book Sorter Activity</h1>
  <div class="muted" id="summary">Loading…</div>
  <div class="grid" id="sessions"></div>
</main>
<script>
function fmtAgo(iso) {
  if (!iso) return 'never';
  const sec = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  return `${hr}h ago`;
}
function fmtDuration(sec) {
  sec = Math.max(0, Number(sec || 0));
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m`;
  const hr = Math.floor(min / 60), rem = min % 60;
  return `${hr}h ${rem}m`;
}
async function load() {
  const data = await fetch('/api/activity', { cache: 'no-store' }).then(r => r.json());
  const sessions = Object.values(data.sessions || {}).sort((a,b) => new Date(b.lastSeen || 0) - new Date(a.lastSeen || 0));
  const active = sessions.filter(s => Date.now() - new Date(s.lastSeen || 0).getTime() < 45000).length;
  document.getElementById('summary').textContent = `${active} active now · ${sessions.length} total browser/device sessions · updated ${fmtAgo(data.updatedAt)}`;
  document.getElementById('sessions').innerHTML = sessions.map(s => {
    const isActive = Date.now() - new Date(s.lastSeen || 0).getTime() < 45000;
    const actions = s.actions || {};
    return `<section class="card">
      <div class="row"><strong>${htmlEscape(s.deviceLabel || 'Unknown device')}</strong><span class="${isActive ? 'active' : 'inactive'}">${isActive ? 'Active now' : 'Last seen ' + fmtAgo(s.lastSeen)}</span></div>
      <p class="muted">First seen: ${new Date(s.firstSeen).toLocaleString()} · Page loads: ${s.pageLoads || 0} · Active time: ${fmtDuration(s.activeSeconds)}</p>
      <p>Keep: ${actions.keep || 0} · Discard: ${actions.discard || 0} · Clear: ${actions.clear || 0} · Category: ${actions.category || 0} · Rotation: ${actions.rotation || 0}</p>
      <p class="muted">Last action: ${s.lastAction ? htmlEscape(s.lastAction.type || 'action') + ' ' + fmtAgo(s.lastAction.at) : 'none yet'}</p>
      <code>${htmlEscape(s.userAgent || '')}</code>
    </section>`;
  }).join('') || '<p class="muted">No activity recorded yet.</p>';
}
function htmlEscape(value) { return String(value).replace(/[&<>"]/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[ch])); }
load(); setInterval(load, 10000);
</script>
</body>
</html>"""


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


@app.get(CONTACT_SHEET_PATH, include_in_schema=False)
def contact_sheet_page():
    return HTMLResponse(CONTACT_SHEET_HTML_PATH.read_text(encoding="utf-8"), headers={"Cache-Control": "no-store"})


@app.get(ADMIN_ACTIVITY_PATH, include_in_schema=False)
def activity_admin_page():
    return HTMLResponse(_activity_admin_html(), headers={"Cache-Control": "no-store"})


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


@app.get("/api/activity", include_in_schema=False)
def get_activity():
    with _activity_lock:
        return _read_activity_unlocked()


@app.post("/api/activity/heartbeat", include_in_schema=False)
def activity_heartbeat(payload: dict[str, Any]):
    with _activity_lock:
        data, session = _upsert_session_unlocked(payload)
        _write_json_unlocked(ACTIVITY_PATH, data)
        return {"ok": True, "session": session, "updatedAt": data["updatedAt"]}


@app.post("/api/activity/action", include_in_schema=False)
def activity_action(payload: dict[str, Any]):
    action_type = str(payload.get("type") or "other")
    if action_type not in {"keep", "discard", "clear", "category", "rotation", "other"}:
        action_type = "other"
    with _activity_lock:
        data, session = _upsert_session_unlocked(payload)
        actions = session.setdefault("actions", {})
        actions[action_type] = int(actions.get(action_type) or 0) + 1
        session["lastAction"] = {
            "type": action_type,
            "at": _now_iso(),
            "bookHash": str(payload.get("bookHash") or "")[:128],
            "label": str(payload.get("label") or "")[:160],
        }
        data["updatedAt"] = _now_iso()
        _write_json_unlocked(ACTIVITY_PATH, data)
        return {"ok": True, "session": session, "updatedAt": data["updatedAt"]}


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")
