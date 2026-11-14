"""Script de verificación integral de Taller 4 - LAB 11:
Rate Limiting + Circuit Breaker + Retry with Backoff en orders-service.

Pruebas:
1. Rate Limiter:
   - Permite hasta 100 peticiones en la ventana de 60 segundos.
   - La petición 101 es rechazada con HTTP 429 Too Many Requests.
   - La respuesta contiene la cabecera 'Retry-After: 60' y el cuerpo '{"error": "Too many requests"}'.
2. Circuit Breaker:
   - Estado inicial: 'closed' (permite peticiones normales).
   - Simulación de fallos consecutivos: al llegar a 5 fallos cambia a 'open'.
   - Con circuito 'open', rechaza llamadas inmediatamente con HTTP 503.
   - Tras el recovery_timeout, pasa a 'half_open' y permite prueba de recuperación.
   - Con respuesta exitosa, vuelve a estado 'closed' y resetea el contador de fallos.
3. Retry with Exponential Backoff:
   - Ejecuta reintentos espaciados exponencialmente (1s, 2s).
   - Recupera el resultado si un reintento tiene éxito.
   - Lanza la última excepción si se agotan los 3 intentos.
"""
import asyncio
import os
import sys
import time

# Configuración utf-8 en Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.abspath("orders-service"))
from dotenv import load_dotenv
load_dotenv("orders-service/.env")

from fastapi.testclient import TestClient
from main import app
from middleware import (
    RateLimiter,
    CircuitBreaker,
    retry_with_backoff,
    rate_limiter,
    catalog_circuit
)

client = TestClient(app)

print("=" * 65)
print("TEST LAB 11: RATE LIMITING + CIRCUIT BREAKER + RETRY WITH BACKOFF")
print("=" * 65)

# ------------------------------------------------------------------------------
# TEST 1: Rate Limiter
# ------------------------------------------------------------------------------
print("\n[TEST 1] Verificando Rate Limiter (100 req / 60s)...")
test_ip = "192.168.1.100"
test_limiter = RateLimiter(max_requests=10, window_seconds=2)

# Las primeras 10 deben permitirse
for i in range(10):
    assert test_limiter.is_allowed(test_ip) is True, f"Fallo en peticion {i+1}"
print("  [OK] 10/10 peticiones permitidas dentro del umbral.")

# La peticion 11 debe bloquearse
assert test_limiter.is_allowed(test_ip) is False, "La peticion 11 debio ser bloqueada"
print("  [OK] Petición 11 bloqueada correctamente (límite alcanzado).")

# Probar limpieza tras expirar la ventana
time.sleep(2.1)
assert test_limiter.is_allowed(test_ip) is True, "Debio permitirse tras expirar la ventana de tiempo"
print("  [OK] Ventana expirada: peticiones anteriores limpiadas y nueva permitida.")

# Probar respuesta HTTP 429 vía TestClient en la API
print("  [API] Probando middleware HTTP 429 en la API de FastAPI...")
rate_limiter.reset()

# Simular que se consumen las 100 peticiones en la instancia global
for i in range(100):
    rate_limiter.is_allowed("testclient")

# La peticion 101 debe devolver HTTP 429 con cabecera Retry-After
resp_429 = client.get("/health")
assert resp_429.status_code == 429, f"Se esperaba 429 pero se obtuvo {resp_429.status_code}"
assert resp_429.headers.get("retry-after") == "60", "Falta cabecera Retry-After: 60"
assert resp_429.json().get("error") == "Too many requests"
print(f"  [OK] Código HTTP 429 capturado correctamente con header 'Retry-After: 60'.")
print(f"       Respuesta: {resp_429.json()}")

# Limpiar para continuar
rate_limiter.reset()


# ------------------------------------------------------------------------------
# TEST 2: Circuit Breaker
# ------------------------------------------------------------------------------
print("\n[TEST 2] Verificando Circuit Breaker (estados CLOSED, OPEN, HALF_OPEN)...")
cb = CircuitBreaker(failure_threshold=5, recovery_timeout=2)

assert cb.state == CircuitBreaker.STATE_CLOSED, "Estado inicial debe ser CLOSED"
assert cb.can_execute() is True
print("  [OK] Estado inicial: CLOSED (permite ejecucion normal).")

# Registrar 4 fallos (aún debe seguir CLOSED)
for _ in range(4):
    cb.record_failure()
assert cb.state == CircuitBreaker.STATE_CLOSED
assert cb.failure_count == 4
print(f"  [OK] Tras 4 fallos consecutivos: estado sigue siendo CLOSED (fallos={cb.failure_count}).")

# Quinto fallo: debe abrir el circuito
cb.record_failure()
assert cb.state == CircuitBreaker.STATE_OPEN
assert cb.can_execute() is False
print("  [OK] Al 5to fallo consecutivo: circuito pasa a OPEN y can_execute() = False.")

# Con circuito abierto, no permite llamadas antes del tiempo de recuperacion
assert cb.can_execute() is False
print("  [OK] Llamadas subsecuentes bloqueadas inmediatamente.")

# Esperar el tiempo de recuperacion para pasar a HALF_OPEN
time.sleep(2.1)
assert cb.can_execute() is True
assert cb.state == CircuitBreaker.STATE_HALF_OPEN
print("  [OK] Transcurridos 2s de recuperación: circuito pasa a HALF_OPEN.")

# Simular éxito en la prueba de recuperación: vuelve a CLOSED
cb.record_success()
assert cb.state == CircuitBreaker.STATE_CLOSED
assert cb.failure_count == 0
print("  [OK] Prueba exitosa: circuito vuelve a CLOSED y resetea fallos a 0.")


# ------------------------------------------------------------------------------
# TEST 3: Retry with Exponential Backoff
# ------------------------------------------------------------------------------
print("\n[TEST 3] Verificando Retry with Exponential Backoff...")

async def run_retry_tests():
    # Caso A: Falla dos veces y tiene éxito en el tercer intento
    intentos_a = 0
    async def op_con_recuperacion():
        nonlocal intentos_a
        intentos_a += 1
        if intentos_a < 3:
            raise ConnectionError(f"Fallo transitorio intento {intentos_a}")
        return "Operación recuperada exitosamente"

    inicio = time.time()
    res_a = await retry_with_backoff(op_con_recuperacion, max_retries=3, base_delay=0.1)
    duracion_a = time.time() - inicio

    assert res_a == "Operación recuperada exitosamente"
    assert intentos_a == 3
    print(f"  [OK] Éxito en intento 3/3 tras retroceso exponencial (duración: {duracion_a:.2f}s).")

    # Caso B: Falla todos los intentos y propaga la excepción
    intentos_b = 0
    async def op_fallo_permanente():
        nonlocal intentos_b
        intentos_b += 1
        raise ValueError(f"Fallo persistente {intentos_b}")

    try:
        await retry_with_backoff(op_fallo_permanente, max_retries=3, base_delay=0.1)
        print("  [ERROR] Debió lanzar excepción!")
        sys.exit(1)
    except ValueError as exc:
        assert intentos_b == 3
        print(f"  [OK] Agotados los 3 reintentos: excepción propagada correctamente ({exc}).")

asyncio.run(run_retry_tests())


# ------------------------------------------------------------------------------
# TEST 4: Endpoints de Resiliencia en la API
# ------------------------------------------------------------------------------
print("\n[TEST 4] Verificando endpoints de monitoreo de resiliencia en la API...")
resp_st = client.get("/resilience/status")
assert resp_st.status_code == 200
status_data = resp_st.json()
print(f"  [OK] GET /resilience/status respondió HTTP 200:")
print(f"       Rate Limiter: {status_data['rate_limiter']}")
print(f"       Circuit Breaker: {status_data['circuit_breaker']}")

# Forzar apertura del Circuit Breaker y consultar espacio
catalog_circuit.reset()
client.post("/resilience/circuit-breaker/trip")
resp_blocked = client.get("/catalog/check/1")
assert resp_blocked.status_code == 503, f"Se esperaba 503 pero se obtuvo {resp_blocked.status_code}"
print(f"  [OK] GET /catalog/check/1 con circuito OPEN retorna HTTP 503 Service Unavailable:")
print(f"       {resp_blocked.json()}")

# Restablecer circuito
client.post("/resilience/circuit-breaker/reset")
assert catalog_circuit.state == "closed"
print("  [OK] Circuit Breaker restablecido a CLOSED.")

print("\n" + "=" * 65)
print("¡TODAS LAS PRUEBAS DE LAB 11 COMPLETADAS CON ÉXITO! (4/4)")
print("=" * 65)
