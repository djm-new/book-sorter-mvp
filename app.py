from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
HTML_PATH = APP_DIR / "books_sorter.html"
SECRET_PATH = "/books/4f8b2d7c"

app = FastAPI(title="Book Sorter MVP")
app.mount("/sample-images", StaticFiles(directory=APP_DIR / "sample-images"), name="sample-images")
app.mount("/sample-crops", StaticFiles(directory=APP_DIR / "sample-crops"), name="sample-crops")


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


@app.get("/robots.txt", include_in_schema=False)
def robots():
    return PlainTextResponse("User-agent: *\nDisallow: /\n")
