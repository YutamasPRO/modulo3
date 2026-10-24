"""orders-service: crea órdenes consultando al catalog-service via HTTP
y consume eventos SpaceChanged desde un Redis Stream."""
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List

import httpx
import redis
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

app = FastAPI(title="Orders Service", version="1.1.0")

# En Docker Compose el hostname es el nombre del servicio.
# En local se puede sobreescribir: CATALOG_URL=http://localhost:8001
CATALOG_URL = os.getenv("CATALOG_URL", "http://catalog-service:8001")
CATALOG_TIMEOUT = float(os.getenv("CATALOG_TIMEOUT", "3.0"))


class Order(BaseModel):
    id: int
    space_id: int
    space_name: str
    user_email: str
    hours: int
    price_per_hour: float
    total_price: float
    created_at: str


ORDERS: List[Order] = []

# --- Consumidor de eventos (equivalente a SQS + Lambda consumer) ---
REDIS_URL = os.getenv("REDIS_URL")
EVENT_STREAM = os.getenv("EVENT_STREAM", "catalog-events")
EVENT_GROUP = os.getenv("EVENT_GROUP", "orders-service")
EVENT_CONSUMER = os.getenv("EVENT_CONSUMER", "orders-1")

# Copia local de la disponibilidad, actualizada por eventos
SPACE_AVAILABILITY: Dict[int, bool] = {}
# Bitácora de eventos recibidos (para evidencia del taller)
EVENT_LOG: List[dict] = []


def handle_event(event: dict) -> None:
    if event.get("detail-type") != "SpaceChanged":
        return
    detail = event["detail"]
    SPACE_AVAILABILITY[detail["space_id"]] = detail["available"]
    EVENT_LOG.append({"received_at": datetime.now(timezone.utc).isoformat(), **event})
    print(f"[consumer] SpaceChanged: espacio {detail['space_id']} -> available={detail['available']}")


def consume_events() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        r.xgroup_create(EVENT_STREAM, EVENT_GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise
    while True:
        try:
            messages = r.xreadgroup(
                EVENT_GROUP, EVENT_CONSUMER, {EVENT_STREAM: ">"}, count=10, block=5000
            )
            for _stream, entries in messages or []:
                for msg_id, fields in entries:
                    handle_event(json.loads(fields["event"]))
                    r.xack(EVENT_STREAM, EVENT_GROUP, msg_id)
        except redis.RedisError as exc:
            print(f"[consumer] error de Redis, reintentando: {exc}")
            time.sleep(3)


@app.on_event("startup")
def start_consumer() -> None:
    if REDIS_URL:
        threading.Thread(target=consume_events, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "healthy", "service": "orders-service"}


@app.post("/orders", response_model=Order)
def create_order(
    space_id: int,
    user_email: str,
    hours: int = Query(..., gt=0, description="Horas a reservar"),
):
    # 1. Consultar al catalog-service (dependencia HTTP síncrona)
    try:
        response = httpx.get(f"{CATALOG_URL}/spaces/{space_id}", timeout=CATALOG_TIMEOUT)
    except httpx.RequestError:
        # Catálogo caído, sin red o con timeout
        raise HTTPException(status_code=503, detail="Catalog service unavailable")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Space {space_id} not found")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Unexpected response from catalog service")

    space = response.json()

    if not space.get("available", True):
        raise HTTPException(status_code=409, detail="Space is not available")

    # 2. Calcular precio. Aquí vive el ACOPLAMIENTO al contrato del catálogo:
    #    si "price_per_hour" cambia de nombre, esta línea lanza KeyError (LAB 5).
    price_per_hour = space["price_per_hour"]

    order = Order(
        id=len(ORDERS) + 1,
        space_id=space_id,
        space_name=space["name"],
        user_email=user_email,
        hours=hours,
        price_per_hour=price_per_hour,
        total_price=price_per_hour * hours,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    ORDERS.append(order)
    return order


@app.get("/orders", response_model=List[Order])
def list_orders():
    return ORDERS


@app.get("/events/log")
def events_log():
    return {"availability": SPACE_AVAILABILITY, "events": EVENT_LOG}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
