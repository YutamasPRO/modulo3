"""orders-service: crea órdenes consultando al catalog-service via HTTP,
persiste en PostgreSQL con SQLAlchemy + Alembic,
gestiona autenticación JWT + RBAC (LAB 10),
y envía eventos/métricas a analytics-service (MongoDB Atlas) y Redis Stream."""
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
import redis
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Depends, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import SessionLocal, get_db
from models import OrderDB, UserDB
from auth import (
    Token,
    UserCreate,
    UserResponse,
    get_password_hash,
    verify_password,
    create_access_token,
    get_current_user,
    require_role
)

app = FastAPI(
    title="Orders Service",
    version="2.0.0",
    description="Microservicio de órdenes con autenticación JWT, RBAC y persistencia PostgreSQL."
)

# Detección inteligente de entorno Docker vs Local
def _is_in_docker() -> bool:
    return os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER") == "true"

_def_cat_host = "catalog-service" if _is_in_docker() else "localhost"
_def_ana_host = "analytics-service" if _is_in_docker() else "localhost"

CATALOG_URL = os.getenv("CATALOG_URL", f"http://{_def_cat_host}:8001")
CATALOG_TIMEOUT = float(os.getenv("CATALOG_TIMEOUT", "3.0"))

# Analytics Service (MongoDB Atlas para métricas y telemetría)
ANALYTICS_URL = os.getenv("ANALYTICS_URL", f"http://{_def_ana_host}:8003")
ANALYTICS_TIMEOUT = float(os.getenv("ANALYTICS_TIMEOUT", "2.0"))


class Order(BaseModel):
    id: int
    space_id: int
    space_name: str
    user_email: str
    hours: int
    price_per_hour: float
    total_price: float
    created_at: str


# --- Consumidor de eventos (equivalente a SQS + Lambda consumer) ---
REDIS_URL = os.getenv("REDIS_URL")
EVENT_STREAM = os.getenv("EVENT_STREAM", "catalog-events")
EVENT_GROUP = os.getenv("EVENT_GROUP", "orders-service")
EVENT_CONSUMER = os.getenv("EVENT_CONSUMER", "orders-1")

SPACE_AVAILABILITY: Dict[int, bool] = {}
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


# ==============================================================================
# LAB 10: Autenticación JWT + Control de Acceso Basado en Roles (RBAC)
# ==============================================================================

@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Registra un nuevo usuario en PostgreSQL con contraseña hasheada mediante bcrypt."""
    existing_user = db.query(UserDB).filter(UserDB.email == user_in.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El correo electrónico ya se encuentra registrado"
        )

    # Validar rol
    valid_roles = ["user", "admin", "superadmin"]
    role = user_in.role if user_in.role in valid_roles else "user"

    hashed_pwd = get_password_hash(user_in.password)
    new_user = UserDB(
        email=user_in.email,
        full_name=user_in.full_name,
        hashed_password=hashed_pwd,
        role=role
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/auth/login", response_model=Token)
async def login_for_access_token(
    request: Request,
    db: Session = Depends(get_db)
):
    """Inicia sesión con credenciales (soporta form-data y JSON), valida hash y retorna token JWT Bearer (60 minutos)."""
    username = None
    password = None
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        try:
            body = await request.json()
            username = body.get("username") or body.get("email")
            password = body.get("password")
        except Exception:
            pass

    if not username:
        try:
            form = await request.form()
            username = form.get("username") or form.get("email")
            password = form.get("password")
        except Exception:
            pass

    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Se requieren los campos 'username' y 'password'"
        )

    user = db.query(UserDB).filter(UserDB.email == username).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role, "email": user.email}
    )
    return Token(access_token=access_token, token_type="bearer")


@app.get("/auth/me", response_model=UserResponse)
def get_user_profile(current_user: UserDB = Depends(get_current_user)):
    """Retorna los datos del usuario autenticado a través del token JWT."""
    return current_user


@app.get("/admin")
@app.get("/admin/dashboard")
async def panel_admin(
    current_user: UserDB = Depends(require_role("admin"))
):
    """Ruta protegida para administradores (requiere rol admin o superadmin)."""
    return {
        "mensaje": "Acceso autorizado al panel de administración",
        "user": current_user.email,
        "role": current_user.role,
        "status": "success",
        "data": {
            "total_users": 15,
            "total_orders": 28,
            "system_health": "100% operativo"
        }
    }


# ==============================================================================
# Endpoints de Órdenes (Persistencia PostgreSQL + Notificación Analytics)
# ==============================================================================

@app.post("/orders", response_model=Order, status_code=status.HTTP_201_CREATED)
async def create_order(
    request: Request,
    space_id: Optional[int] = Query(None),
    user_email: Optional[str] = Query(None),
    hours: Optional[int] = Query(None),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Crea una orden en PostgreSQL. Requiere autenticación JWT. Extrae el correo del token."""
    # 1. Leer parámetros desde JSON body o Query params
    body_data = {}
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            body_data = await request.json()
        except Exception:
            pass

    target_space_id = body_data.get("space_id") if body_data.get("space_id") is not None else space_id
    if target_space_id is None:
        raise HTTPException(status_code=400, detail="El campo 'space_id' es requerido")

    target_hours = body_data.get("hours") or hours or 2

    # El usuario autenticado prevalece para user_email (seguridad JWT)
    target_user_email = current_user.email

    # Determinar precio y nombre del espacio
    space_name = f"Espacio #{target_space_id}"
    price_per_hour = 25.0
    total_price = body_data.get("total_price")

    # Intentar consultar catalog-service si está disponible
    try:
        response = httpx.get(
            f"{CATALOG_URL}/spaces/{target_space_id}",
            timeout=CATALOG_TIMEOUT
        )
        if response.status_code == 200:
            space = response.json()
            space_name = space.get("name", space_name)
            price_per_hour = space.get("price_per_hour", price_per_hour)
            if not space.get("available", True):
                raise HTTPException(status_code=409, detail="Space is not available")
    except HTTPException:
        raise
    except Exception:
        # Modo resiliente
        pass

    if total_price is None:
        total_price = price_per_hour * target_hours

    # 2. Persistir en PostgreSQL vía SQLAlchemy
    try:
        new_order = OrderDB(
            space_id=target_space_id,
            space_name=space_name,
            user_email=target_user_email,
            hours=target_hours,
            price_per_hour=price_per_hour,
            total_price=float(total_price)
        )

        db.add(new_order)
        db.commit()
        db.refresh(new_order)

        order_data = Order(
            id=new_order.id,
            space_id=new_order.space_id,
            space_name=new_order.space_name,
            user_email=new_order.user_email,
            hours=new_order.hours,
            price_per_hour=new_order.price_per_hour,
            total_price=new_order.total_price,
            created_at=new_order.created_at.isoformat()
        )

        # 3. Notificar a analytics-service (MongoDB Atlas)
        if ANALYTICS_URL:
            try:
                httpx.post(
                    f"{ANALYTICS_URL}/orders",
                    json={
                        "order_id": new_order.id,
                        "space_id": new_order.space_id,
                        "space_name": new_order.space_name,
                        "user_email": new_order.user_email,
                        "hours": new_order.hours,
                        "price_per_hour": new_order.price_per_hour,
                        "total_price": new_order.total_price,
                        "created_at": new_order.created_at.isoformat()
                    },
                    timeout=ANALYTICS_TIMEOUT
                )
            except Exception:
                pass

        return order_data
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        print(f"[error] Error guardando orden en PostgreSQL: {exc}")
        raise HTTPException(status_code=500, detail=f"Error creando orden: {exc}")


@app.get("/orders", response_model=List[Order])
def list_orders():
    db = SessionLocal()
    try:
        orders = db.query(OrderDB).order_by(OrderDB.id).all()
        return [
            Order(
                id=order.id,
                space_id=order.space_id,
                space_name=order.space_name,
                user_email=order.user_email,
                hours=order.hours,
                price_per_hour=order.price_per_hour,
                total_price=order.total_price,
                created_at=order.created_at.isoformat()
            )
            for order in orders
        ]
    except Exception as exc:
        print(f"[error] Error consultando órdenes: {exc}")
        raise HTTPException(status_code=500, detail="Error retrieving orders")
    finally:
        db.close()


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: int):
    db = SessionLocal()
    try:
        order = db.query(OrderDB).filter(OrderDB.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        return Order(
            id=order.id,
            space_id=order.space_id,
            space_name=order.space_name,
            user_email=order.user_email,
            hours=order.hours,
            price_per_hour=order.price_per_hour,
            total_price=order.total_price,
            created_at=order.created_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as exc:
        print(f"[error] Error consultando orden {order_id}: {exc}")
        raise HTTPException(status_code=500, detail="Error retrieving order")
    finally:
        db.close()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run(app, host="0.0.0.0", port=port)
