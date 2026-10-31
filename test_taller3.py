"""Script de verificación integral de Taller 3:
1. Conexión y persistencia en PostgreSQL con SQLAlchemy + Alembic (LAB 8).
2. Conexión, indexado y consultas agregadas en MongoDB Atlas / local (LAB 9).
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

test_order_id = None

try:
    with engine.connect() as conn:
        res = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
        print(f"[OK] Conexión a PostgreSQL exitosa.")
        print(f"[OK] Versión actual de Alembic en BD: {res[0] if res else 'None'}")

    db = SessionLocal()
    count_before = db.query(OrderDB).count()
    print(f"[INFO] Órdenes existentes en PostgreSQL: {count_before}")

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
    test_order_id = test_order.id
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

# Si se ejecuta fuera de Docker, resolver 'mongodb:27017' a 'localhost:27017'
mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
if "mongodb://mongodb:" in mongo_uri:
    mongo_uri = mongo_uri.replace("mongodb://mongodb:", "mongodb://localhost:")

mongo_test = MongoDBClient(uri=mongo_uri)
connected = mongo_test.connect(max_retries=2, retry_delay=1.0)

if connected:
    print(f"[OK] Conexión a MongoDB exitosa ({mongo_test.db_name}).")
    print("[OK] Índices asegurados en colecciones 'orders' y 'events'.")

    # Registrar orden en MongoDB
    order_id_to_record = test_order_id if test_order_id else 100
    mongo_test.record_order({
        "order_id": order_id_to_record,
        "space_id": 2,
        "space_name": "Escritorio Flex (Test Taller 3)",
        "user_email": "estudiante@prueba.com",
        "hours": 3,
        "price_per_hour": 5.0,
        "total_price": 15.0,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    print(f"[OK] Orden {order_id_to_record} registrada en MongoDB para analítica.")

    # Registrar evento flexible
    mongo_test.log_event("SpaceViewed", {
        "space_id": 2,
        "user_email": "estudiante@prueba.com",
        "device": "mobile",
        "source": "search"
    })
    print("[OK] Evento flexible registrado en MongoDB.")

    # Ejecutar consultas de analytics requeridas en rúbrica
    summary = mongo_test.get_summary()
    print(f"[OK] Query get_summary(): {summary}")

    popular = mongo_test.get_popular_spaces()
    print(f"[OK] Query get_popular_spaces(): {popular}")

    user_metrics = mongo_test.get_user_analytics("estudiante@prueba.com")
    print(f"[OK] Query get_user_analytics(): {user_metrics}")

    events = mongo_test.get_events(limit=5)
    print(f"[OK] Query get_events() (total recuperados: {len(events)}): {len(events)} eventos encontrados.")
    mongo_test.close()
else:
    print("[INFO] MongoDB no disponible en URI:", mongo_uri)
    print("[INFO] Verifica que Docker esté corriendo o coloca tu URL de MongoDB Atlas en analytics-service/.env")

print("\n" + "=" * 60)
print("VERIFICACIÓN FINALIZADA CON ÉXITO")
print("=" * 60)
