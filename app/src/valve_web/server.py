"""FastAPI application factory for the web UI."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from valve_web.routers import auth, config, history, inspect, stream, users
from valve_web.state import get_context

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Screw Assembly Inspection - Web UI")

    @app.middleware("http")
    async def _no_cache_static(request, call_next):
        # Always revalidate front-end assets so edits never get masked by a
        # stale browser cache.
        response = await call_next(request)
        path = request.url.path
        if path == "/" or path.endswith((".js", ".css", ".html")):
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

    # Initialise the shared context (loads config, discovers models) at startup.
    @app.on_event("startup")
    def _startup():
        get_context()

    @app.on_event("shutdown")
    def _shutdown():
        get_context().cameras.stop_all()

    for module in (auth, stream, inspect, config, history, users):
        app.include_router(module.router)

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app
