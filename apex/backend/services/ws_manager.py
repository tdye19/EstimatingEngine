"""WebSocket connection manager for real-time pipeline status push.

Usage
-----
From async code (WebSocket endpoint):
    await ws_manager.connect(project_id, websocket)
    await ws_manager.disconnect(project_id, websocket)
    await ws_manager.broadcast(project_id, message_dict)

From sync code (orchestrator background thread):
    ws_manager.broadcast_sync(project_id, message_dict)

Call ws_manager.set_loop(asyncio.get_running_loop()) once during app startup
so that broadcast_sync can schedule coroutines on the main event loop.
"""

import asyncio
import json
import logging
from collections import defaultdict

logger = logging.getLogger("apex.ws_manager")


class ConnectionManager:
    """Thread-safe manager for per-project WebSocket connections.

    Maintains a mapping of project_id → set[WebSocket].  All mutations to the
    mapping are guarded by an asyncio.Lock so concurrent connection/disconnect
    events from multiple coroutines are safe.

    The sync broadcast path (broadcast_sync) uses
    asyncio.run_coroutine_threadsafe so the orchestrator background thread can
    push updates without having its own event loop.

    A separate batch_connections dict handles batch-import channels so that
    group_id values never collide with project_id keys.
    """

    def __init__(self) -> None:
        # project_id -> set of active WebSocket connections
        self._connections: dict[int, set] = defaultdict(set)
        # group_id -> set of active WebSocket connections (batch-import channel)
        self._batch_connections: dict[int, set] = defaultdict(set)
        self._lock = asyncio.Lock()
        # Stored during app startup so sync callers can schedule coroutines
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # Startup hook
    # ------------------------------------------------------------------

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Store the running event loop.  Call once in the app lifespan."""
        self._loop = loop
        logger.debug("WS manager event loop registered")

    # ------------------------------------------------------------------
    # Connection lifecycle (async)
    # ------------------------------------------------------------------

    async def connect(self, project_id: int, websocket) -> None:
        """Accept the WebSocket handshake and register the connection."""
        await websocket.accept()
        async with self._lock:
            self._connections[project_id].add(websocket)
        count = len(self._connections[project_id])
        logger.info("WS connected — project %s (active: %d)", project_id, count)

    async def disconnect(self, project_id: int, websocket) -> None:
        """Remove a connection from the registry."""
        async with self._lock:
            self._connections[project_id].discard(websocket)
            if not self._connections[project_id]:
                del self._connections[project_id]
        logger.info("WS disconnected — project %s", project_id)

    # ------------------------------------------------------------------
    # Broadcasting
    # ------------------------------------------------------------------

    async def broadcast(self, project_id: int, message: dict) -> None:
        """Send *message* as JSON to every client watching *project_id*.

        Dead connections (those that raise on send) are silently removed.
        """
        payload = json.dumps(message)
        async with self._lock:
            clients = list(self._connections.get(project_id, set()))
        if not clients:
            return

        dead: list = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections[project_id].discard(ws)

    def broadcast_sync(self, project_id: int, message: dict) -> None:
        """Fire-and-forget broadcast from a synchronous (non-async) context.

        Safe to call from the orchestrator background thread.  Silently
        no-ops if the event loop has not been registered or has stopped.
        """
        if self._loop is None or not self._loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.broadcast(project_id, message),
                self._loop,
            )
        except Exception as exc:
            logger.debug("broadcast_sync scheduling failed: %s", exc)

    # ------------------------------------------------------------------
    # Batch-import connection lifecycle (async)
    # ------------------------------------------------------------------

    async def connect_batch(self, group_id: int, websocket) -> None:
        """Accept a batch-import WebSocket and register it under group_id."""
        await websocket.accept()
        async with self._lock:
            self._batch_connections[group_id].add(websocket)
        count = len(self._batch_connections[group_id])
        logger.info("WS batch connected — group %s (active: %d)", group_id, count)

    async def disconnect_batch(self, group_id: int, websocket) -> None:
        """Remove a batch-import connection from the registry."""
        async with self._lock:
            self._batch_connections[group_id].discard(websocket)
            if not self._batch_connections[group_id]:
                del self._batch_connections[group_id]
        logger.info("WS batch disconnected — group %s", group_id)

    async def broadcast_batch(self, group_id: int, message: dict) -> None:
        """Send *message* as JSON to every client watching *group_id*."""
        payload = json.dumps(message)
        async with self._lock:
            clients = list(self._batch_connections.get(group_id, set()))
        if not clients:
            return

        dead: list = []
        for ws in clients:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    self._batch_connections[group_id].discard(ws)

    def broadcast_batch_sync(self, group_id: int, message: dict) -> None:
        """Fire-and-forget batch broadcast from a synchronous context."""
        if self._loop is None or not self._loop.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self.broadcast_batch(group_id, message),
                self._loop,
            )
        except Exception as exc:
            logger.debug("broadcast_batch_sync scheduling failed: %s", exc)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def has_connections(self, project_id: int) -> bool:
        """Return True if at least one client is watching *project_id*."""
        return bool(self._connections.get(project_id))


# Module-level singleton — import this everywhere
ws_manager = ConnectionManager()
