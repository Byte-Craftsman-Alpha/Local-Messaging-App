from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .connection_manager import RoomManager


BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Local Messaging Rooms")
rooms = RoomManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/rooms")
async def create_room(request: Request) -> JSONResponse:
    body: Dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    password = body.get("password") if isinstance(body, dict) else None
    password = password if isinstance(password, str) else None

    room_id = secrets.token_urlsafe(8)
    await rooms.ensure_room(room_id)
    await rooms.set_room_password(room_id, password)
    room_url = str(request.base_url).rstrip("/") + f"/room/{room_id}"
    return JSONResponse({"room_id": room_id, "room_url": room_url})


@app.get("/api/rooms/{room_id}")
async def get_room(room_id: str) -> JSONResponse:
    protected = await rooms.is_room_protected(room_id)
    return JSONResponse({"room_id": room_id, "protected": protected})


@app.get("/room/{room_id}", response_class=HTMLResponse)
async def room_page(request: Request, room_id: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "room.html",
        {
            "request": request,
            "room_id": room_id,
        },
    )


@app.get("/r/{room_id}")
async def room_short(room_id: str) -> RedirectResponse:
    return RedirectResponse(url=f"/room/{room_id}")


@app.websocket("/ws/{room_id}")
async def ws_room(websocket: WebSocket, room_id: str) -> None:
    await rooms.connect(room_id, websocket)
    is_authed = False

    async def require_auth() -> bool:
        nonlocal is_authed
        protected = await rooms.is_room_protected(room_id)
        if not protected:
            is_authed = True
            await websocket.send_json(
                {"type": "auth_ok", "ts": datetime.now(timezone.utc).isoformat()}
            )
            return True

        await websocket.send_json(
            {"type": "auth_required", "ts": datetime.now(timezone.utc).isoformat()}
        )
        try:
            data: Dict[str, Any] = await websocket.receive_json()
        except Exception:
            await websocket.close(code=1008)
            return False

        if data.get("type") != "auth":
            await websocket.send_json(
                {
                    "type": "auth_error",
                    "message": "Authentication required",
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
            await websocket.close(code=1008)
            return False

        password = data.get("password")
        password = password if isinstance(password, str) else ""
        ok = await rooms.verify_room_password(room_id, password)
        if not ok:
            await websocket.send_json(
                {
                    "type": "auth_error",
                    "message": "Invalid room password",
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
            )
            await websocket.close(code=1008)
            return False

        is_authed = True
        await websocket.send_json(
            {"type": "auth_ok", "ts": datetime.now(timezone.utc).isoformat()}
        )
        return True

    async def broadcast_presence() -> None:
        users = await rooms.get_online_users(room_id)
        await rooms.broadcast_ephemeral(
            room_id,
            {
                "type": "presence",
                "users": users,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    try:
        authed = await require_auth()
        if not authed:
            return

        history = await rooms.get_history(room_id)
        for msg in history:
            await websocket.send_json(msg)

        await broadcast_presence()

        while True:
            data: Dict[str, Any] = await websocket.receive_json()

            if not is_authed:
                continue

            msg_type = data.get("type")
            if msg_type == "presence":
                username = (data.get("username") or "").strip()
                if not username:
                    continue
                await rooms.set_username(room_id, websocket, username)
                await broadcast_presence()
                continue

            if msg_type == "typing":
                username = (data.get("username") or "").strip()
                is_typing = bool(data.get("is_typing"))
                if not username:
                    continue

                payload = {
                    "type": "typing",
                    "username": username,
                    "is_typing": is_typing,
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                await rooms.broadcast_ephemeral(room_id, payload)
                continue

            if msg_type != "chat":
                continue

            username = (data.get("username") or "Anonymous").strip() or "Anonymous"
            message = (data.get("message") or "").strip()
            if not message:
                continue

            payload = {
                "type": "chat",
                "username": username,
                "message": message,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            await rooms.broadcast(room_id, payload)

    except WebSocketDisconnect:
        await rooms.disconnect(room_id, websocket)
        await broadcast_presence()
    except Exception:
        await rooms.disconnect(room_id, websocket)
        await broadcast_presence()
        try:
            await websocket.close()
        except Exception:
            return
