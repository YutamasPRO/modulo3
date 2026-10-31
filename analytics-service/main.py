"""analytics-service: Servicio de analítica y métricas de uso basado en MongoDB Atlas.
Almacena órdenes para reportería flexible y captura telemetría/eventos."""
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from mongodb_client import mongo_client

app = FastAPI(title="Analytics Service", version="1.0.0")

# Integración opcional con Redis Stream si se requiere captura asíncrona de eventos
REDIS_URL = os.getenv("REDIS_URL")
EVENT_STREAM = os.getenv("EVENT_STREAM", "catalog-events")
EVENT_GROUP = os.getenv("EVENT_GROUP", "analytics-service")
EVENT_CONSUMER = os.getenv("EVENT_CONSUMER", "analytics-1")


class OrderAnalyticsPayload(BaseModel):
    order_id: int
    space_id: int
    space_name: str
    user_email: str
    hours: int
    price_per_hour: float
    total_price: float
    created_at: Optional[str] = None


class EventPayload(BaseModel):
    event_type: str
    data: Dict[str, Any]


def handle_stream_event(event: dict) -> None:
    """Registra eventos de Redis en MongoDB como telemetría."""
    event_type = event.get("detail-type", "UnknownEvent")
    detail = event.get("detail", {})
    mongo_client.log_event(event_type, detail)
    print(f"[analytics-consumer] Evento capturado en MongoDB: {event_type}")


def consume_events() -> None:
    if not REDIS_URL:
        return
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
                    handle_stream_event(json.loads(fields["event"]))
                    r.xack(EVENT_STREAM, EVENT_GROUP, msg_id)
        except redis.RedisError as exc:
            print(f"[analytics-consumer] Error de Redis: {exc}")
            time.sleep(3)


@app.on_event("startup")
def startup_event():
    # Conexión resiliente a MongoDB Atlas
    connected = mongo_client.connect()
    if connected:
        print("[analytics-service] Conectado exitosamente a MongoDB Atlas.")
    else:
        print("[analytics-service] Advertencia: MongoDB no disponible en arranque. Se reintentará por demanda.")

    if REDIS_URL:
        threading.Thread(target=consume_events, daemon=True).start()


@app.on_event("shutdown")
def shutdown_event():
    mongo_client.close()


@app.get("/health")
def health():
    db_connected = mongo_client.is_connected()
    return {
        "status": "healthy" if db_connected else "degraded",
        "service": "analytics-service",
        "database": "mongodb-atlas" if db_connected else "disconnected"
    }


# ==========================================
# Ingesta de Datos (Orders y Eventos)
# ==========================================

@app.post("/orders")
def record_order(payload: OrderAnalyticsPayload):
    """Recibe órdenes desde orders-service y las indexa en MongoDB Atlas."""
    success = mongo_client.record_order(payload.model_dump())
    if not success:
        # Si la base de datos está caída, devolvemos 503 pero no bloqueamos
        raise HTTPException(status_code=503, detail="No se pudo registrar la orden en MongoDB")
    return {"status": "recorded", "order_id": payload.order_id}


@app.post("/events")
def record_event(payload: EventPayload):
    """Registra eventos flexibles de telemetría y uso (clicks, búsquedas, etc.)."""
    success = mongo_client.log_event(payload.event_type, payload.data)
    if not success:
        raise HTTPException(status_code=503, detail="No se pudo registrar el evento en MongoDB")
    return {"status": "recorded", "event_type": payload.event_type}


# ==========================================
# Consultas de Analytics (Criterio: Queries)
# ==========================================

@app.get("/analytics/summary")
def get_summary():
    """KPIs agregados de facturación y ocupación."""
    return mongo_client.get_summary()


@app.get("/analytics/popular-spaces")
def get_popular_spaces():
    """Espacios más reservados con métricas agregadas."""
    return mongo_client.get_popular_spaces()


@app.get("/analytics/user/{email}")
def get_user_analytics(email: str):
    """Métricas y patrón de uso de un cliente específico."""
    return mongo_client.get_user_analytics(email)


@app.get("/analytics/events")
def list_events(
    event_type: Optional[str] = Query(None, description="Filtrar por tipo de evento"),
    limit: int = Query(50, gt=0, le=200, description="Cantidad máxima de eventos a recuperar")
):
    """Consulta la bitácora de eventos y logs en MongoDB."""
    return mongo_client.get_events(event_type=event_type, limit=limit)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8003"))
    uvicorn.run(app, host="0.0.0.0", port=port)

