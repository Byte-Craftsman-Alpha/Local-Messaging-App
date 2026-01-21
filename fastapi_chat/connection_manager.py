from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket


@dataclass
class Room:
    connections: Set[WebSocket] = field(default_factory=set)
    history: List[Dict[str, Any]] = field(default_factory=list)
    usernames: Dict[WebSocket, str] = field(default_factory=dict)
    password_hash: Optional[str] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RoomManager:
    def __init__(self, *, history_limit: int = 200) -> None:
        self._rooms: Dict[str, Room] = {}
        self._rooms_lock = asyncio.Lock()
        self._history_limit = history_limit

    def _hash_password(self, password: str) -> str:
        iterations = 150_000
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        salt_b64 = base64.b64encode(salt).decode("ascii")
        dk_b64 = base64.b64encode(dk).decode("ascii")
        return f"pbkdf2_sha256${iterations}${salt_b64}${dk_b64}"

    def _verify_password(self, stored: str, candidate: str) -> bool:
        try:
            scheme, iterations_str, salt_b64, dk_b64 = stored.split("$", 3)
            if scheme != "pbkdf2_sha256":
                return False
            iterations = int(iterations_str)
            salt = base64.b64decode(salt_b64.encode("ascii"))
            expected = base64.b64decode(dk_b64.encode("ascii"))
            actual = hashlib.pbkdf2_hmac(
                "sha256", candidate.encode("utf-8"), salt, iterations
            )
            return hmac.compare_digest(expected, actual)
        except Exception:
            return False

    async def ensure_room(self, room_id: str) -> None:
        async with self._rooms_lock:
            if room_id not in self._rooms:
                self._rooms[room_id] = Room()

    async def set_room_password(self, room_id: str, password: Optional[str]) -> None:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        normalized = (password or "").strip()
        async with room.lock:
            room.password_hash = self._hash_password(normalized) if normalized else None

    async def is_room_protected(self, room_id: str) -> bool:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        async with room.lock:
            return bool(room.password_hash)

    async def verify_room_password(self, room_id: str, candidate: str) -> bool:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        async with room.lock:
            stored = room.password_hash
        if not stored:
            return True
        return self._verify_password(stored, candidate)

    async def get_history(self, room_id: str) -> List[Dict[str, Any]]:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        async with room.lock:
            return list(room.history)

    async def connect(self, room_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        async with room.lock:
            room.connections.add(websocket)
            room.usernames.setdefault(websocket, "")

    async def disconnect(self, room_id: str, websocket: WebSocket) -> None:
        if room_id not in self._rooms:
            return
        room = self._rooms[room_id]
        async with room.lock:
            room.connections.discard(websocket)
            room.usernames.pop(websocket, None)

    async def set_username(self, room_id: str, websocket: WebSocket, username: str) -> None:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        async with room.lock:
            if websocket in room.connections:
                room.usernames[websocket] = username

    async def get_online_users(self, room_id: str) -> List[str]:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]
        async with room.lock:
            names = [n.strip() for n in room.usernames.values() if n and n.strip()]
        unique = sorted(set(names), key=lambda s: s.lower())
        return unique

    async def broadcast(self, room_id: str, payload: Dict[str, Any]) -> None:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]

        async with room.lock:
            room.history.append(payload)
            if len(room.history) > self._history_limit:
                room.history = room.history[-self._history_limit :]

            connections = list(room.connections)

        if not connections:
            return

        await asyncio.gather(
            *[self._safe_send_json(ws, payload) for ws in connections],
            return_exceptions=True,
        )

    async def broadcast_ephemeral(self, room_id: str, payload: Dict[str, Any]) -> None:
        await self.ensure_room(room_id)
        room = self._rooms[room_id]

        async with room.lock:
            connections = list(room.connections)

        if not connections:
            return

        await asyncio.gather(
            *[self._safe_send_json(ws, payload) for ws in connections],
            return_exceptions=True,
        )

    async def _safe_send_json(self, websocket: WebSocket, payload: Dict[str, Any]) -> None:
        try:
            await websocket.send_json(payload)
        except Exception:
            return
