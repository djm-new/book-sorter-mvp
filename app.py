from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, PlainTextResponse

APP_DIR = Path(__file__).resolve().parent
HTML_PATH = APP_DIR / "books_sorter.html"
DEMO_PHOTO = APP_DIR / "books-sorter-demo.jpg"
SECRET_PATH = "/books/4f8b2d7c"

app = FastAPI(title="Book Sorter MVP")


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


@app.get("/books/demo-photo", include_in_schema=False)
def demo_photo():
    return FileResponse(DEMO_PHOTO, media_type="image/jpeg")


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")
