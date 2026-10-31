"""Script de verificación integral de Taller 3:
1. Conexión y persistencia en PostgreSQL con SQLAlchemy + Alembic.
2. Conexión, indexado y consultas agregadas en MongoDB Atlas / local.
"""
import os
import sys

# Asegurar codificación utf-8 en terminales Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timezone

# 1. Probar PostgreSQL (LAB 8)
print("=" * 60)
print("TEST 1: PostgreSQL + SQLAlchemy + Alembic (LAB 8)")
print("=" * 60)

sys.path.insert(0, os.path.abspath("orders-service"))
from dotenv import load_dotenv
load_dotenv("orders-service/.env")

from database import engine, SessionLocal
from models import OrderDB
from sqlalchemy import text

try:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        print(f"[OK] Conexión a PostgreSQL exitosa.")
        print(f"[OK] Versión actual de Alembic en BD: {res[0] if res else 'None'}")

    db = SessionLocal()
    count_before = db.query(OrderDB).count()
    print(f"[INFO] Órdenes actuales en PostgreSQL: {count_before}")

    # Probar creación de orden de prueba
    test_order = OrderDB(
        space_id=2,
        space_name="Escritorio Flex (Test Taller 3)",
        user_email="estudiante@prueba.com",
        hours=3,
        price_per_hour=5.0,
        total_price=15.0
    )
    db.add(test_order)
    db.commit()
    db.refresh(test_order)
    print(f"[OK] Orden de prueba creada en PostgreSQL con ID: {test_order.id}")
    db.close()
except Exception as e:
    print(f"[ERROR] Error en PostgreSQL: {e}")

# 2. Probar MongoDB Atlas / local (LAB 9)
print("\n" + "=" * 60)
print("TEST 2: MongoDB Atlas + Índices + Queries de Analytics (LAB 9)")
print("=" * 60)

sys.path.insert(0, os.path.abspath("analytics-service"))
load_dotenv("analytics-service/.env")

from mongodb_client import MongoDBClient

# Si no hay MongoDB activo en 27017 o Atlas, informamos con claridad
mongo_test = MongoDBClient()
connected = mongo_test.connect(max_retries=1)

if connected:
    print("[OK] Conexión a MongoDB exitosa.")
    print("[OK] Índices asegurados en colecciones 'orders' y 'events'.")

    # Registrar orden
    mongo_test.record_order({
        "order_id": test_order.id if 'test_order' in locals() else 999,
        "space_id": 2,
        "space_name": "Escritorio Flex (Test Taller 3)",
        "user_email": "estudiante@prueba.com",
        "hours": 3,
        "price_per_hour": 5.0,
        "total_price": 15.0,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    print("[OK] Orden registrada en MongoDB para analítica.")

    # Registrar evento flexible
    mongo_test.log_event("SpaceViewed", {
        "space_id": 2,
        "user_email": "estudiante@prueba.com",
        "device": "mobile",
        "source": "search"
    })
    print("[OK] Evento flexible registrado en MongoDB.")

    # Ejecutar consultas de analytics
    summary = mongo_test.get_summary()
    print(f"[OK] Query get_summary(): {summary}")

    popular = mongo_test.get_popular_spaces()
    print(f"[OK] Query get_popular_spaces(): {popular}")

    user_metrics = mongo_test.get_user_analytics("estudiante@prueba.com")
    print(f"[OK] Query get_user_analytics(): {user_metrics}")

    events = mongo_test.get_events(limit=5)
    print(f"[OK] Query get_events() (total recuperados: {len(events)}): {events[:2]}")
    mongo_test.close()
else:
    print("[INFO] MongoDB no disponible en esta máquina localmente (puerto 27017).")
    print("[INFO] Para probar MongoDB: inicia Docker con 'docker compose up -d' o coloca tu cadena de conexión de MongoDB Atlas en analytics-service/.env")

print("\n" + "=" * 60)
print("VERIFICACIÓN FINALIZADA")
print("=" * 60)
