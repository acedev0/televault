from __future__ import annotations

import asyncio
import contextlib
import math
import secrets
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .config import AppSecrets, ConfigurationError, SecretVault, resolve_data_dir
from .database import Database
from .indexer import IndexManager
from .ranges import RangeNotSatisfiable, parse_range_header
from .security import LoginRateLimiter, new_token, verify_password
from .telegram_client import TelegramMediaClient


PACKAGE_DIR = Path(__file__).resolve().parent


def format_bytes(value: int | str | None) -> str:
    size = float(value or 0)
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return "0 B"


def format_duration(value: int | str | None) -> str:
    seconds = max(0, int(value or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def format_date(value: str | None) -> str:
    if not value:
        return "Unknown date"
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.strftime("%b %-d, %Y")
    except (ValueError, TypeError):
        return value


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "PUT", "PATCH"}:
            content_length = int(request.headers.get("content-length", "0") or 0)
            if content_length > 16 * 1024:
                return Response("Request too large", status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; "
            "form-action 'self'; object-src 'none'; img-src 'self' data:; "
            "media-src 'self'; style-src 'self'; script-src 'self'",
        )
        return response


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _is_authenticated(request: Request, config: AppSecrets) -> bool:
    stored = str(request.session.get("user", ""))
    return bool(request.session.get("authenticated")) and secrets.compare_digest(
        stored, config.web_username
    )


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = new_token(24)
        request.session["csrf"] = token
    return str(token)


def _valid_csrf(request: Request, supplied: str) -> bool:
    expected = str(request.session.get("csrf", ""))
    return bool(expected and supplied and secrets.compare_digest(expected, supplied))


def _auth_redirect(request: Request, config: AppSecrets) -> RedirectResponse | None:
    if _is_authenticated(request, config):
        return None
    return RedirectResponse("/login", status_code=303)


def create_app(
    data_dir: str | Path | None = None,
    telegram_factory: Callable[[AppSecrets], Any] | None = None,
) -> FastAPI:
    selected_data_dir = resolve_data_dir(data_dir)
    vault = SecretVault(selected_data_dir)
    try:
        config = vault.load()
        config_error = ""
    except ConfigurationError as exc:
        config = None
        config_error = str(exc)

    database = Database(selected_data_dir / "televault.db")
    database.initialise()
    limiter = LoginRateLimiter()
    templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
    templates.env.filters["filesize"] = format_bytes
    templates.env.filters["duration"] = format_duration
    templates.env.filters["date"] = format_date

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.telegram = None
        application.state.telegram_error = config_error
        application.state.indexer = None
        application.state.periodic_task = None
        application.state.sync_job = None
        if config is not None:
            factory = telegram_factory or TelegramMediaClient
            telegram = factory(config)
            application.state.telegram = telegram
            try:
                await telegram.connect()
                indexer = IndexManager(
                    database, telegram, selected_data_dir / "thumbnails"
                )
                application.state.indexer = indexer
                application.state.telegram_error = ""

                async def periodic_sync() -> None:
                    while True:
                        await asyncio.sleep(max(60, config.sync_interval_seconds))
                        try:
                            await indexer.scan(full=False)
                        except Exception as exc:
                            application.state.telegram_error = str(exc)

                application.state.periodic_task = asyncio.create_task(periodic_sync())
            except Exception as exc:
                application.state.telegram_error = str(exc)
        try:
            yield
        finally:
            for task_name in ("periodic_task", "sync_job"):
                task = getattr(application.state, task_name, None)
                if task and not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
            telegram = getattr(application.state, "telegram", None)
            if telegram is not None:
                with contextlib.suppress(Exception):
                    await telegram.disconnect()

    app = FastAPI(
        title="TeleVault",
        version="1.2.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.cookie_secret if config else new_token(48),
        session_cookie="televault_session",
        max_age=12 * 60 * 60,
        same_site="strict",
        https_only=False,
    )
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    @app.get("/healthz")
    async def healthz(request: Request) -> JSONResponse:
        connected = bool(
            getattr(request.app.state, "telegram", None)
            and not getattr(request.app.state, "telegram_error", "")
        )
        return JSONResponse(
            {
                "status": "ok" if config and connected else "degraded",
                "configured": config is not None,
                "telegram_connected": connected,
            }
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if config and _is_authenticated(request, config):
            return RedirectResponse("/", status_code=303)
        response = templates.TemplateResponse(
            request,
            "login.html",
            {
                "csrf": _csrf_token(request),
                "error": "",
                "configuration_error": config_error,
            },
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/login", response_class=HTMLResponse)
    async def login_submit(request: Request):
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        csrf = str(form.get("csrf", ""))
        identity = _client_ip(request)
        allowed, retry_after = await limiter.allowed(identity)
        error = "Invalid username or password."
        status = 401
        if not allowed:
            error = f"Too many attempts. Try again in {math.ceil(retry_after / 60)} minute(s)."
            status = 429
        elif config is None:
            error = config_error
            status = 503
        elif not _valid_csrf(request, csrf):
            error = "Your login page expired. Refresh and try again."
            status = 403
        elif secrets.compare_digest(username, config.web_username) and verify_password(
            config.password_hash, password
        ):
            await limiter.success(identity)
            request.session.clear()
            request.session["authenticated"] = True
            request.session["user"] = config.web_username
            request.session["csrf"] = new_token(24)
            return RedirectResponse("/", status_code=303)
        else:
            await limiter.failure(identity)

        response = templates.TemplateResponse(
            request,
            "login.html",
            {
                "csrf": _csrf_token(request),
                "error": error,
                "configuration_error": config_error,
            },
            status_code=status,
        )
        response.headers["Cache-Control"] = "no-store"
        if status == 429:
            response.headers["Retry-After"] = str(retry_after)
        return response

    @app.post("/logout")
    async def logout(request: Request):
        form = await request.form()
        if not _valid_csrf(request, str(form.get("csrf", ""))):
            return Response("Invalid CSRF token", status_code=403)
        request.session.clear()
        response = RedirectResponse("/login", status_code=303)
        response.delete_cookie("televault_session")
        return response

    @app.get("/", response_class=HTMLResponse)
    async def library(request: Request):
        if config is None:
            return RedirectResponse("/login", status_code=303)
        redirect = _auth_redirect(request, config)
        if redirect:
            return redirect
        query = request.query_params.get("q", "")[:120]
        kind = request.query_params.get("kind", "all")
        sort = request.query_params.get("sort", "newest")
        kind = kind if kind in {"all", "video", "photo"} else "all"
        sort = sort if sort in {"newest", "oldest", "name", "largest"} else "newest"
        batch_size = 36
        items, total = database.list_media(
            query=query,
            kind=kind,
            per_page=batch_size,
            sort=sort,
            offset=0,
        )
        response = templates.TemplateResponse(
            request,
            "library.html",
            {
                "items": items,
                "total": total,
                "stats": database.stats(),
                "query": query,
                "kind": kind,
                "sort": sort,
                "has_more": len(items) < total,
                "csrf": _csrf_token(request),
                "config": config,
                "last_scan_at": database.get_meta("last_scan_at"),
                "telegram_error": request.app.state.telegram_error,
            },
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/api/media", response_class=HTMLResponse)
    async def media_batch(request: Request):
        if config is None or not _is_authenticated(request, config):
            return Response(status_code=401)
        query = request.query_params.get("q", "")[:120]
        kind = request.query_params.get("kind", "all")
        sort = request.query_params.get("sort", "newest")
        kind = kind if kind in {"all", "video", "photo"} else "all"
        sort = sort if sort in {"newest", "oldest", "name", "largest"} else "newest"
        try:
            offset = max(0, int(request.query_params.get("offset", "0")))
        except ValueError:
            offset = 0
        batch_size = 36
        items, total = database.list_media(
            query=query,
            kind=kind,
            per_page=batch_size,
            sort=sort,
            offset=offset,
        )
        next_offset = offset + len(items)
        response = templates.TemplateResponse(
            request,
            "media_cards.html",
            {"items": items},
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Next-Offset"] = str(next_offset)
        response.headers["X-Has-More"] = "true" if next_offset < total else "false"
        response.headers["X-Total-Count"] = str(total)
        return response

    @app.get("/media/{media_id}", response_class=HTMLResponse)
    async def media_page(media_id: int, request: Request):
        if config is None:
            return RedirectResponse("/login", status_code=303)
        redirect = _auth_redirect(request, config)
        if redirect:
            return redirect
        item = database.get_media(media_id)
        if item is None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"title": "Media not found", "message": "This item is no longer indexed."},
                status_code=404,
            )
        response = templates.TemplateResponse(
            request,
            "media.html",
            {
                "item": item,
                "related": database.related(media_id, item["kind"]),
                "csrf": _csrf_token(request),
                "config": config,
            },
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.get("/thumbnail/{media_id}")
    async def thumbnail(media_id: int, request: Request):
        if config is None or not _is_authenticated(request, config):
            return Response(status_code=401)
        item = database.get_media(media_id)
        if item is None or not item.get("thumbnail_filename"):
            return FileResponse(PACKAGE_DIR / "static" / "placeholder.svg", media_type="image/svg+xml")
        path = selected_data_dir / "thumbnails" / Path(item["thumbnail_filename"]).name
        if not path.is_file():
            return FileResponse(PACKAGE_DIR / "static" / "placeholder.svg", media_type="image/svg+xml")
        return FileResponse(
            path,
            media_type="image/webp",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    @app.api_route("/stream/{media_id}", methods=["GET", "HEAD"])
    async def stream_media(media_id: int, request: Request):
        if config is None or not _is_authenticated(request, config):
            return Response(status_code=401)
        item = database.get_media(media_id)
        telegram = request.app.state.telegram
        if item is None or telegram is None:
            return Response("Media unavailable", status_code=404)
        if request.app.state.telegram_error:
            return Response("Telegram is temporarily unavailable", status_code=503)
        filename = quote(str(item["filename"]), safe="")
        base_headers = {
            "Accept-Ranges": "bytes",
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"inline; filename*=UTF-8''{filename}",
            "X-Accel-Buffering": "no",
        }
        if item["kind"] == "photo":
            if request.method == "HEAD":
                return Response(headers=base_headers, media_type=item["mime_type"])
            try:
                raw = await telegram.download_photo(int(item["message_id"]))
            except FileNotFoundError:
                return Response("Media unavailable", status_code=404)
            base_headers["Content-Length"] = str(len(raw))
            return Response(raw, media_type=item["mime_type"], headers=base_headers)

        size = int(item["size_bytes"] or 0)
        try:
            selected = parse_range_header(request.headers.get("range"), size)
        except RangeNotSatisfiable:
            return Response(
                status_code=416,
                headers={**base_headers, "Content-Range": f"bytes */{max(0, size)}"},
            )
        message = await telegram.get_message(int(item["message_id"]))
        if message is None:
            return Response("Media unavailable", status_code=404)
        headers = {**base_headers, "Content-Length": str(selected.length)}
        status_code = 206 if selected.partial else 200
        if selected.partial:
            headers["Content-Range"] = selected.content_range
        if request.method == "HEAD":
            return Response(
                status_code=status_code,
                media_type=item["mime_type"],
                headers=headers,
            )
        return StreamingResponse(
            telegram.stream(
                int(item["message_id"]),
                selected.start,
                selected.end,
                selected.size,
            ),
            status_code=status_code,
            media_type=item["mime_type"],
            headers=headers,
        )

    @app.post("/sync")
    async def start_sync(request: Request):
        if config is None or not _is_authenticated(request, config):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        form = await request.form()
        if not _valid_csrf(request, str(form.get("csrf", ""))):
            return JSONResponse({"error": "invalid_csrf"}, status_code=403)
        indexer = request.app.state.indexer
        if indexer is None:
            return JSONResponse(
                {"error": request.app.state.telegram_error or "Telegram is offline"},
                status_code=503,
            )
        job = request.app.state.sync_job
        if job and not job.done():
            return JSONResponse({"status": "already_running"}, status_code=202)

        async def run_sync() -> None:
            try:
                await indexer.scan(full=False)
                request.app.state.telegram_error = ""
            except Exception as exc:
                request.app.state.telegram_error = str(exc)

        request.app.state.sync_job = asyncio.create_task(run_sync())
        return JSONResponse({"status": "started"}, status_code=202)

    @app.get("/api/status")
    async def sync_status(request: Request):
        if config is None or not _is_authenticated(request, config):
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        indexer = request.app.state.indexer
        status = asdict(indexer.status) if indexer else None
        return JSONResponse(
            {
                "telegram_error": request.app.state.telegram_error,
                "index": status,
                "stats": database.stats(),
                "last_scan_at": database.get_meta("last_scan_at"),
            }
        )

    return app
