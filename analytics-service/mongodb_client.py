import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "coworking_analytics")

# Configuración de Connection Pool y Timeouts (Criterio: Manejo de conexiones y pool)
MAX_POOL_SIZE = int(os.getenv("MONGO_MAX_POOL_SIZE", "50"))
MIN_POOL_SIZE = int(os.getenv("MONGO_MIN_POOL_SIZE", "5"))
SERVER_SELECTION_TIMEOUT_MS = int(os.getenv("MONGO_TIMEOUT_MS", "5000"))


class MongoDBClient:
    """Cliente de MongoDB Atlas con soporte de pool de conexiones, reintentos y queries de analítica."""

    def __init__(self, uri: Optional[str] = None, db_name: Optional[str] = None):
        self.uri = uri or MONGO_URI
        self.db_name = db_name or MONGO_DB_NAME
        self.client: Optional[MongoClient] = None
        self.db = None
        self._connected = False

    def connect(self, max_retries: int = 3, retry_delay: float = 2.0) -> bool:
        """Conexión resiliente a MongoDB Atlas con reintentos y pool de conexiones."""
        for attempt in range(1, max_retries + 1):
            try:
                print(f"[mongodb] Conectando a MongoDB Atlas (intento {attempt}/{max_retries})...")
                self.client = MongoClient(
                    self.uri,
                    maxPoolSize=MAX_POOL_SIZE,
                    minPoolSize=MIN_POOL_SIZE,
                    serverSelectionTimeoutMS=SERVER_SELECTION_TIMEOUT_MS,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=5000,
                    retryWrites=True,
                )
                # Ping al servidor para forzar verificación de credenciales y conectividad
                self.client.admin.command("ping")
                self.db = self.client[self.db_name]
                self._connected = True
                print(f"[mongodb] Conexión exitosa a base de datos: {self.db_name}")
                self.ensure_indexes()
                return True
            except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
                print(f"[mongodb] Intento {attempt} fallido: {exc}")
                if attempt < max_retries:
                    time.sleep(retry_delay)
                else:
                    print("[mongodb] No se pudo conectar a MongoDB tras los reintentos.")
                    self._connected = False
                    return False
            except Exception as exc:
                print(f"[mongodb] Error inesperado: {exc}")
                self._connected = False
                return False
        return False

    def is_connected(self) -> bool:
        if not self._connected or not self.client:
            return False
        try:
            self.client.admin.command("ping")
            return True
        except Exception:
            return False

    def close(self):
        """Cierra el pool de conexiones a MongoDB."""
        if self.client:
            self.client.close()
            self._connected = False
            print("[mongodb] Conexión cerrada.")

    def ensure_indexes(self):
        """Crea índices en las colecciones para optimizar consultas de analytics (Criterio: Índices)."""
        if self.db is None:
            return
        try:
            # Índices para la colección de órdenes analíticas
            orders_col = self.db["orders"]
            orders_col.create_index([("order_id", ASCENDING)], unique=True)
            orders_col.create_index([("user_email", ASCENDING)])
            orders_col.create_index([("space_id", ASCENDING)])
            orders_col.create_index([("created_at", DESCENDING)])
            orders_col.create_index([("user_email", ASCENDING), ("created_at", DESCENDING)])

            # Índices para la colección de eventos flexibles / telemetría
            events_col = self.db["events"]
            events_col.create_index([("timestamp", DESCENDING)])
            events_col.create_index([("event_type", ASCENDING)])
            events_col.create_index([("space_id", ASCENDING)])
            events_col.create_index([("space_id", ASCENDING), ("timestamp", DESCENDING)])

            print("[mongodb] Índices creados correctamente en orders y events.")
        except Exception as exc:
            print(f"[mongodb] Advertencia creando índices: {exc}")

    # ==========================================
    # Inserciones y Registro de Telemetría
    # ==========================================

    def record_order(self, order_data: Dict[str, Any]) -> bool:
        """Registra o actualiza una orden sincronizada para analytics."""
        if not self.is_connected():
            return False
        try:
            doc = dict(order_data)
            if "created_at" not in doc or not doc["created_at"]:
                doc["created_at"] = datetime.now(timezone.utc).isoformat()
            doc["synced_at"] = datetime.now(timezone.utc).isoformat()

            self.db["orders"].update_one(
                {"order_id": doc["order_id"]},
                {"$set": doc},
                upsert=True
            )
            return True
        except Exception as exc:
            print(f"[mongodb] Error registrando orden: {exc}")
            return False

    def log_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Registra un evento con esquema flexible en MongoDB (logs de uso, vistas, clicks, cambios)."""
        if not self.is_connected():
            return False
        try:
            event_doc = {
                "event_type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            if "space_id" in data:
                event_doc["space_id"] = data["space_id"]
            if "user_email" in data:
                event_doc["user_email"] = data["user_email"]

            self.db["events"].insert_one(event_doc)
            return True
        except Exception as exc:
            print(f"[mongodb] Error registrando evento: {exc}")
            return False

    # ==========================================
    # Queries de Analytics (Aggregation Pipelines)
    # ==========================================

    def get_summary(self) -> Dict[str, Any]:
        """Calcula KPIs globales: total órdenes, ingresos, horas y usuarios únicos."""
        if not self.is_connected():
            return {"status": "error", "message": "MongoDB no conectado"}

        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_orders": {"$sum": 1},
                    "total_revenue": {"$sum": "$total_price"},
                    "total_hours": {"$sum": "$hours"},
                    "avg_order_value": {"$avg": "$total_price"},
                    "avg_hours": {"$avg": "$hours"},
                    "unique_users": {"$addToSet": "$user_email"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "total_orders": 1,
                    "total_revenue": {"$round": ["$total_revenue", 2]},
                    "total_hours": 1,
                    "avg_order_value": {"$round": ["$avg_order_value", 2]},
                    "avg_hours": {"$round": ["$avg_hours", 2]},
                    "unique_users_count": {"$size": "$unique_users"}
                }
            }
        ]
        results = list(self.db["orders"].aggregate(pipeline))
        if results:
            return results[0]
        return {
            "total_orders": 0,
            "total_revenue": 0.0,
            "total_hours": 0,
            "avg_order_value": 0.0,
            "avg_hours": 0.0,
            "unique_users_count": 0
        }

    def get_popular_spaces(self) -> List[Dict[str, Any]]:
        """Espacios más reservados ordenados por volumen de reservas y facturación."""
        if not self.is_connected():
            return []

        pipeline = [
            {
                "$group": {
                    "_id": {
                        "space_id": "$space_id",
                        "space_name": "$space_name"
                    },
                    "total_bookings": {"$sum": 1},
                    "total_hours": {"$sum": "$hours"},
                    "total_revenue": {"$sum": "$total_price"},
                    "avg_duration": {"$avg": "$hours"}
                }
            },
            {
                "$sort": {"total_bookings": -1, "total_revenue": -1}
            },
            {
                "$project": {
                    "_id": 0,
                    "space_id": "$_id.space_id",
                    "space_name": "$_id.space_name",
                    "total_bookings": 1,
                    "total_hours": 1,
                    "total_revenue": {"$round": ["$total_revenue", 2]},
                    "avg_duration": {"$round": ["$avg_duration", 2]}
                }
            }
        ]
        return list(self.db["orders"].aggregate(pipeline))

    def get_user_analytics(self, user_email: str) -> Dict[str, Any]:
        """Perfil de comportamiento y gasto de un usuario."""
        if not self.is_connected():
            return {"status": "error", "message": "MongoDB no conectado"}

        pipeline = [
            {"$match": {"user_email": user_email}},
            {
                "$group": {
                    "_id": "$user_email",
                    "total_orders": {"$sum": 1},
                    "total_spent": {"$sum": "$total_price"},
                    "total_hours": {"$sum": "$hours"},
                    "spaces_booked": {"$addToSet": "$space_name"}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "user_email": "$_id",
                    "total_orders": 1,
                    "total_spent": {"$round": ["$total_spent", 2]},
                    "total_hours": 1,
                    "spaces_booked": 1
                }
            }
        ]
        results = list(self.db["orders"].aggregate(pipeline))
        if results:
            return results[0]
        return {
            "user_email": user_email,
            "total_orders": 0,
            "total_spent": 0.0,
            "total_hours": 0,
            "spaces_booked": []
        }

    def get_events(self, event_type: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Recupera los logs de eventos más recientes."""
        if not self.is_connected():
            return []
        query = {"event_type": event_type} if event_type else {}
        cursor = self.db["events"].find(query, {"_id": 0}).sort("timestamp", DESCENDING).limit(limit)
        return list(cursor)


# Instancia compartida
mongo_client = MongoDBClient()
