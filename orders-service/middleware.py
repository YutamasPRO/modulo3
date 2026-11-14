"""Módulo de Middleware y Resiliencia para orders-service (LAB 11)
Implementa:
1. Rate Limiter: Limita las peticiones por IP (100 req / 60s). Retorna 429 Too Many Requests.
2. Circuit Breaker: Estados CLOSED, OPEN, HALF_OPEN con umbral de 5 fallos y 60s de recuperación. Retorna 503 Service Unavailable.
3. Retry with Backoff: Reintenta operaciones fallidas hasta 3 veces con esperas exponenciales (1s, 2s).
"""
import asyncio
import time
from collections import defaultdict
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import httpx


# ==============================================================================
# 2. RATE LIMITER: Limitar las solicitudes
# ==============================================================================

class RateLimiter:
    """Limita la cantidad de solicitudes que puede realizar una dirección IP en una ventana de tiempo."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, client_id: str) -> bool:
        """Comprueba si la solicitud está permitida dentro de la ventana de tiempo."""
        now = time.time()
        # Eliminar las solicitudes con más de window_seconds (60s)
        self.requests[client_id] = [
            t for t in self.requests[client_id]
            if now - t < self.window_seconds
        ]

        # Si ya alcanzó el límite, bloquear la nueva solicitud
        if len(self.requests[client_id]) >= self.max_requests:
            return False

        # Si todavía no alcanza el límite, registrar y permitir
        self.requests[client_id].append(now)
        return True

    def reset(self, client_id: Optional[str] = None):
        """Reinicia el contador de solicitudes para pruebas."""
        if client_id:
            self.requests.pop(client_id, None)
        else:
            self.requests.clear()


# Instancia global del Rate Limiter
rate_limiter = RateLimiter(max_requests=100, window_seconds=60)


async def rate_limit_middleware(request: Request, call_next):
    """Middleware de FastAPI para interceptar cada petición y aplicar el Rate Limiter."""
    # Excluir rutas de documentación, dashboard visual y gestión de resiliencia
    if request.url.path in ["/", "/dashboard", "/docs", "/redoc", "/openapi.json"] or request.url.path.startswith("/resilience/"):
        return await call_next(request)

    # Identificar la dirección IP del cliente (considerando encabezados X-Forwarded-For)
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "127.0.0.1"

    if not rate_limiter.is_allowed(client_ip):
        return JSONResponse(
            status_code=429,
            content={"error": "Too many requests"},
            headers={"Retry-After": "60"}
        )

    response = await call_next(request)
    return response


# ==============================================================================
# 3. CIRCUIT BREAKER: Proteger servicios externos
# ==============================================================================

class CircuitBreaker:
    """Implementa el patrón Circuit Breaker con estados CLOSED, OPEN y HALF_OPEN."""

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half_open"

    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = self.STATE_CLOSED

    def can_execute(self) -> bool:
        """Decide si se permite llamar al servicio externo según el estado actual."""
        now = time.time()
        if self.state == self.STATE_CLOSED:
            return True
        elif self.state == self.STATE_OPEN:
            # Comprobar si ya transcurrieron los segundos de recuperación
            if now - self.last_failure_time > self.recovery_timeout:
                self.state = self.STATE_HALF_OPEN
                return True
            return False
        elif self.state == self.STATE_HALF_OPEN:
            # Permite una prueba de recuperación
            return True
        return False

    def record_success(self):
        """Reinicia el contador de errores y cierra el circuito al responder correctamente."""
        self.failure_count = 0
        self.state = self.STATE_CLOSED

    def record_failure(self):
        """Aumenta el contador de fallos. Al alcanzar el umbral, abre el circuito."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = self.STATE_OPEN

    def reset(self):
        """Fuerza el circuito al estado cerrado y limpia contadores."""
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = self.STATE_CLOSED


# Instancia global del Circuit Breaker para el catálogo
catalog_circuit = CircuitBreaker(failure_threshold=5, recovery_timeout=60)


async def call_catalog_with_breaker(url: str, timeout_sec: float = 5.0) -> dict:
    """Conecta con catalog-service protegiendo la llamada con el Circuit Breaker."""
    if not catalog_circuit.can_execute():
        raise HTTPException(
            status_code=503,
            detail="Catalog service circuit breaker is OPEN (service temporarily unavailable)"
        )

    try:
        async with httpx.AsyncClient(timeout=timeout_sec) as client:
            response = await client.get(url)
            if response.status_code == 200:
                catalog_circuit.record_success()
                return response.json()
            elif response.status_code == 404:
                # 404 es una respuesta válida del negocio (no un fallo del servicio)
                return response.json()
            else:
                catalog_circuit.record_failure()
                raise HTTPException(
                    status_code=503,
                    detail=f"Catalog service returned status {response.status_code}"
                )
    except httpx.RequestError as exc:
        catalog_circuit.record_failure()
        raise HTTPException(
            status_code=503,
            detail=f"Catalog service call failed: {exc}"
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        catalog_circuit.record_failure()
        raise HTTPException(
            status_code=503,
            detail=f"Unexpected error calling catalog: {exc}"
        )


# ==============================================================================
# 4. RETRY WITH BACKOFF: Reintentar operaciones
# ==============================================================================

async def retry_with_backoff(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0
) -> Any:
    """Reintenta una función asíncrona hasta max_retries veces con retardo exponencial."""
    last_exception = None

    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"Retry {attempt + 1}/{max_retries} after {delay}s: {str(e)}")
                await asyncio.sleep(delay)

    raise last_exception
