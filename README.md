# Coworking Workshop – Taller 3: Bases de Datos en la Nube

Arquitectura de microservicios con persistencia en la nube:
* **`catalog-service`**: Microservicio en FastAPI que expone los espacios de coworking y publica eventos de disponibilidad (`SpaceChanged`).
* **`orders-service` (LAB 8)**: Microservicio en FastAPI que gestiona y persiste órdenes en **PostgreSQL** mediante **SQLAlchemy** y migraciones de esquema con **Alembic**.
* **`analytics-service` (LAB 9)**: Microservicio en FastAPI conectado a **MongoDB Atlas** para análisis flexible de métricas, KPIs agregados (ingresos, ocupación, usuarios) y bitácora de telemetría con índices y pool de conexiones.

---

## 🏗️ Arquitectura del Sistema

```
                  ┌──────────────────────┐
                  │   catalog-service    │ (Puerto 8001)
                  └──────────┬───────────┘
                             │ HTTP /spaces/{id}
                             ▼
┌──────────────────┐  HTTP   ┌──────────────────────┐  SQLAlchemy   ┌──────────────────────┐
│  analytics-svc   │◄────────┤    orders-service    ├──────────────►│    PostgreSQL        │
│  (MongoDB Atlas) │  POST   └──────────────────────┘   + Alembic   │ (AWS RDS / Render)   │
└─────────┬────────┘                                                └──────────────────────┘
          │
          ▼
┌──────────────────┐
│ MongoDB Atlas    │
│ (Métricas, Logs) │
└──────────────────┘
```

---

## 📋 Mapeo con Criterios de Evaluación

| Criterio | Implementación | Archivo Clave |
|---|---|---|
| **PostgreSQL RDS / Render configurado y accesible** | Conexión SQLAlchemy con soporte `postgresql://`, variables de entorno y validación. | `orders-service/database.py` |
| **Migraciones con Alembic funcionando** | Configuración `env.py`, historial de versiones en `alembic/versions` y ejecución automática en despliegue. | `orders-service/alembic.ini`, `orders-service/alembic/env.py` |
| **MongoDB Atlas conectado con índices** | Conexión resiliente a MongoDB con creación automática de índices en `orders` y `events`. | `analytics-service/mongodb_client.py` |
| **Queries de analytics correctos** | Aggregation pipelines para KPIs (ingresos totales, promedio, popularidad de espacios, métricas de usuario). | `analytics-service/mongodb_client.py`, `analytics-service/main.py` |
| **Manejo de conexiones (pool, retry)** | Pool en SQLAlchemy (`pool_size`, `max_overflow`, `pool_pre_ping`) y pool en PyMongo (`maxPoolSize`, `minPoolSize`, reintentos ante desconexión). | `orders-service/database.py`, `analytics-service/mongodb_client.py` |

---

## 🚀 Ejecución Rápida Local (Docker Compose)

Para levantar todos los microservicios junto con MongoDB local:

```bash
docker compose up -d --build
```

Verificar el estado de salud de los tres servicios:

```bash
# Windows PowerShell o Bash:
curl http://localhost:8001/health   # Catálogo
curl http://localhost:8002/health   # Órdenes (PostgreSQL)
curl http://localhost:8003/health   # Analytics (MongoDB)
```

---

## 🧪 Pruebas de Funcionamiento

### 1. Crear una orden (PostgreSQL + Notificación a Analytics)
```bash
curl -X POST "http://localhost:8002/orders?space_id=1&user_email=estudiante@ejemplo.com&hours=3"
```
*Respuesta:* La orden se inserta con ID autoincremental en PostgreSQL y se replica inmediatamente a MongoDB Atlas.

### 2. Consultar órdenes en PostgreSQL
```bash
curl http://localhost:8002/orders
```

### 3. Consultar Resumen de Métricas (KPIs en MongoDB Atlas)
```bash
curl http://localhost:8003/analytics/summary
```
*Ejemplo de salida:*
```json
{
  "total_orders": 3,
  "total_revenue": 175.0,
  "total_hours": 9,
  "avg_order_value": 58.33,
  "avg_hours": 3.0,
  "unique_users_count": 2
}
```

### 4. Consultar Espacios Populares
```bash
curl http://localhost:8003/analytics/popular-spaces
```

### 5. Registrar y Consultar Eventos Flexibles
```bash
# Registrar un evento de búsqueda:
curl -X POST -H "Content-Type: application/json" -d "{\"event_type\": \"SpaceSearch\", \"data\": {\"user_email\": \"estudiante@ejemplo.com\", \"capacity\": 8}}" http://localhost:8003/events

# Ver eventos registrados:
curl http://localhost:8003/analytics/events
```

---

## ☁️ Guía de Despliegue en Render

### 1. Variables de Entorno en Render
En tu panel de Render (Render Dashboard):

1. **`orders-service`**:
   - `PORT`: `8002`
   - `CATALOG_URL`: `http://catalog-service:8001`
   - `ANALYTICS_URL`: `http://analytics-service:8003`
   - `DATABASE_URL`: Tu URL de PostgreSQL de Render o AWS RDS:
     ```
     postgresql://usuario:password@host.render.com:5432/nombre_bd
     ```

2. **`analytics-service`**:
   - `PORT`: `8003`
   - `MONGO_URI`: Tu cadena de conexión de MongoDB Atlas:
     ```
     mongodb+srv://<usuario>:<password>@cluster0.xxxx.mongodb.net/?retryWrites=true&w=majority
     ```
   - `MONGO_DB_NAME`: `coworking_analytics`

### 2. Despliegue con Blueprint (`render.yaml`)
El archivo `render.yaml` ya incluye la definición de los servicios:
1. Conecta tu repositorio de GitHub a Render.
2. Selecciona **New +** -> **Blueprint**.
3. Selecciona tu repositorio `modulo3`.
4. Render creará automáticamente los servicios web y el Redis privado.
5. Asigna los valores de `DATABASE_URL` y `MONGO_URI` en los ajustes de cada servicio.

---

## 🗄️ Migraciones con Alembic (LAB 8)

Para ejecutar o gestionar migraciones en el microservicio de órdenes:

```bash
cd orders-service

# Crear una nueva migración automática basada en models.py:
alembic revision --autogenerate -m "descripcion_cambio"

# Aplicar las migraciones a la base de datos:
alembic upgrade head

# Ver la versión actual en la base de datos:
alembic current
```

> **Nota:** El `Dockerfile` de `orders-service` ejecuta automáticamente `python -m alembic upgrade head` al iniciar el contenedor, garantizando que la base de datos en la nube siempre esté al día.
