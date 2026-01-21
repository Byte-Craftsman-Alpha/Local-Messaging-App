from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .connection_manager import RoomManager


BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Local Messaging Rooms")
rooms = RoomManager()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/rooms")
async def create_room(request: Request) -> JSONResponse:
    room_id = secrets.token_urlsafe(8)
    await rooms.ensure_room(room_id)
    room_url = str(request.base_url).rstrip("/") + f"/room/{room_id}"
    return JSONResponse({"room_id": room_id, "room_url": room_url})


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

    try:
        history = await rooms.get_history(room_id)
        for msg in history:
            await websocket.send_json(msg)

        while True:
            data: Dict[str, Any] = await websocket.receive_json()

            msg_type = data.get("type")
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
    except Exception:
        await rooms.disconnect(room_id, websocket)
        try:
            await websocket.close()
        except Exception:
            return
