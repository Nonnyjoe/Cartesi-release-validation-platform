"""
GET /queues — return RabbitMQ queue depths by querying the management API
"""
from fastapi import APIRouter
from datetime import datetime, timezone
import os, httpx

router = APIRouter(prefix="/queues", tags=["queues"])

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_MGMT_PORT = int(os.getenv("RABBITMQ_MGMT_PORT", "15672"))
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "rvp")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "rvp_secret")
RABBITMQ_VHOST = os.getenv("RABBITMQ_VHOST", "rvp")

MGMT_URL = f"http://{RABBITMQ_HOST}:{RABBITMQ_MGMT_PORT}/api/queues/{RABBITMQ_VHOST}"


@router.get("")
async def queue_depths():
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            resp = await client.get(MGMT_URL, auth=(RABBITMQ_USER, RABBITMQ_PASS))
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            return {"queues": [], "fetched_at": datetime.now(timezone.utc).isoformat(), "error": str(e)}

    queues = [
        {
            "name": q.get("name"),
            "messages": q.get("messages", 0),
            "consumers": q.get("consumers", 0),
            "message_stats": q.get("message_stats"),
        }
        for q in data
    ]
    queues.sort(key=lambda q: q["name"])
    return {"queues": queues, "fetched_at": datetime.now(timezone.utc).isoformat()}
