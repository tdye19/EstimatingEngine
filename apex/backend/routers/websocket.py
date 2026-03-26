"""WebSocket endpoint for real-time pipeline status updates.

Endpoint: ws://<host>/ws/pipeline/{project_id}

Protocol
--------
Server → Client messages (JSON):
  {"type": "pipeline_update", "project_id": ..., "overall": ..., "agents": [...], ...}
  {"type": "pipeline_complete", ...}
  {"type": "pipeline_error", ...}
  {"type": "ping"}          — server keepalive heartbeat

Client → Server messages (text):
  "ping"                    — client keepalive; server replies "pong"

Lifecycle
---------
1. Client connects → server immediately sends the current DB-backed snapshot.
2. Orchestrator broadcasts updates via ws_manager.broadcast_sync().
3. A server-side ping is sent every HEARTBEAT_INTERVAL seconds of silence.
4. If the client sends no message for IDLE_TIMEOUT_S seconds the server
   closes the connection (safety net; well-behaved clients ping every 30 s).
"""

import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apex.backend.services.ws_manager import ws_manager

router = APIRouter()
logger = logging.getLogger("apex.ws")

HEARTBEAT_INTERVAL = 30    # seconds: how often to ping a silent client
IDLE_TIMEOUT_S = 300       # 5 minutes: close truly idle connections


@router.websocket("/ws/pipeline/{project_id}")
async def pipeline_websocket(project_id: int, websocket: WebSocket):
    await ws_manager.connect(project_id, websocket)
    try:
        # Push current status snapshot immediately so the client has data
        # before the first orchestrator broadcast arrives.
        await _send_initial_status(project_id, websocket)

        last_message_at = datetime.now(timezone.utc)

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_INTERVAL
                )
                last_message_at = datetime.now(timezone.utc)
                if raw == "ping":
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                # Client has been silent; send a keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break  # connection dropped

                # Close after extended idle (client pings every 30 s normally)
                idle_s = (datetime.now(timezone.utc) - last_message_at).total_seconds()
                if idle_s >= IDLE_TIMEOUT_S:
                    logger.info(
                        "Closing idle WS for project %s (idle %.0fs)", project_id, idle_s
                    )
                    await websocket.close(code=1000)
                    break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WS error for project %s: %s", project_id, exc)
    finally:
        await ws_manager.disconnect(project_id, websocket)


@router.websocket("/ws/batch-import/{group_id}")
async def batch_import_websocket(group_id: int, websocket: WebSocket):
    await ws_manager.connect_batch(group_id, websocket)
    try:
        last_message_at = datetime.now(timezone.utc)

        while True:
            try:
                raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_INTERVAL
                )
                last_message_at = datetime.now(timezone.utc)
                if raw == "ping":
                    await websocket.send_text("pong")

            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

                idle_s = (datetime.now(timezone.utc) - last_message_at).total_seconds()
                if idle_s >= IDLE_TIMEOUT_S:
                    logger.info(
                        "Closing idle WS for batch group %s (idle %.0fs)", group_id, idle_s
                    )
                    await websocket.close(code=1000)
                    break

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WS error for batch group %s: %s", group_id, exc)
    finally:
        await ws_manager.disconnect_batch(group_id, websocket)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _send_initial_status(project_id: int, websocket: WebSocket) -> None:
    """Push the current DB-backed pipeline state to a freshly connected client."""
    from apex.backend.db.database import SessionLocal
    from apex.backend.services.agent_orchestrator import AgentOrchestrator

    db = SessionLocal()
    try:
        orchestrator = AgentOrchestrator(db, project_id)
        statuses = orchestrator.get_pipeline_status()

        status_values = [s["status"] for s in statuses]
        if any(v == "running" for v in status_values):
            overall = "running"
        elif any(v == "failed" for v in status_values):
            overall = "failed"
        elif all(v in ("completed", "skipped") for v in status_values):
            overall = "completed"
        elif all(v == "pending" for v in status_values):
            overall = "pending"
        else:
            overall = "pending"

        await websocket.send_json({
            "type": "pipeline_update",
            "project_id": project_id,
            "overall": overall,
            "agents": statuses,
        })
    except Exception as exc:
        logger.warning(
            "Could not send initial WS status for project %s: %s", project_id, exc
        )
    finally:
        db.close()
