"""catalog-service: expone los espacios de coworking via HTTP
y publica eventos SpaceChanged en un Redis Stream cuando cambia la disponibilidad."""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional

import redis
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Catalog Service", version="1.1.0")

# Redis (Key Value en Render). Si no hay REDIS_URL, el servicio sigue
# funcionando pero no publica eventos.
REDIS_URL = os.getenv("REDIS_URL")
EVENT_STREAM = os.getenv("EVENT_STREAM", "catalog-events")
_redis: Optional[redis.Redis] = redis.from_url(REDIS_URL, decode_responses=True) if REDIS_URL else None


def publish_event(event_type: str, detail: dict) -> Optional[str]:
    """Publica un evento en el stream (equivalente a EventBridge + SQS)."""
    if _redis is None:
        return None
    event = {
        "source": "catalog-service",
        "detail-type": event_type,
        "time": datetime.now(timezone.utc).isoformat(),
        "detail": detail,
    }
    try:
        return _redis.xadd(EVENT_STREAM, {"event": json.dumps(event)})
    except redis.RedisError:
        return None


class Space(BaseModel):
    id: int
    name: str
    capacity: int
    price_per_hour: float
    available: bool = True


# "Base de datos" en memoria
SPACES: List[Space] = [
    Space(id=1, name="Sala Innovación", capacity=8, price_per_hour=25.0),
    Space(id=2, name="Escritorio Flex", capacity=1, price_per_hour=5.0),
    Space(id=3, name="Sala de Juntas Premium", capacity=12, price_per_hour=40.0),
    Space(id=4, name="Cabina Silenciosa", capacity=1, price_per_hour=8.0, available=False),
]


@app.get("/health")
def health():
    return {"status": "healthy", "service": "catalog-service"}


@app.get("/spaces", response_model=List[Space])
def list_spaces():
    return SPACES


@app.get("/spaces/{space_id}", response_model=Space)
def get_space(space_id: int):
    for space in SPACES:
        if space.id == space_id:
            return space
    raise HTTPException(status_code=404, detail=f"Space {space_id} not found")


class AvailabilityUpdate(BaseModel):
    available: bool


@app.put("/spaces/{space_id}/availability", response_model=Space)
def update_availability(space_id: int, body: AvailabilityUpdate):
    for space in SPACES:
        if space.id == space_id:
            changed = space.available != body.available
            space.available = body.available
            if changed:
                publish_event(
                    "SpaceChanged",
                    {"space_id": space.id, "name": space.name, "available": space.available},
                )
            return space
    raise HTTPException(status_code=404, detail=f"Space {space_id} not found")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
