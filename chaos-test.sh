#!/usr/bin/env bash
# LAB 4 - Chaos Engineering: apagar el catálogo y observar el comportamiento de orders-service.
set -u

ORDERS_URL="http://localhost:8002/orders?space_id=1&user_email=chaos@test.com&hours=2"

# Soporta tanto "docker-compose" (v1) como "docker compose" (v2)
if command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC="docker compose"
fi

call_orders() {
  # Imprime código HTTP, tiempo de respuesta y cuerpo
  curl -s -o /tmp/chaos_body.txt -w "HTTP %{http_code} | tiempo: %{time_total}s\n" -X POST "$ORDERS_URL"
  echo "Respuesta: $(cat /tmp/chaos_body.txt)"
  echo
}

echo "=== 1. Estado normal (esperado: 200 OK) ==="
call_orders

echo "=== 2. Apagando catalog-service ==="
$DC stop catalog-service
sleep 2
echo "=== Petición con catálogo caído (esperado: 503 Catalog service unavailable) ==="
call_orders

echo "=== 3. Recuperando catalog-service ==="
$DC start catalog-service
echo "Esperando a que el catálogo esté listo..."
for i in $(seq 1 20); do
  if curl -s -f http://localhost:8001/health >/dev/null; then
    echo "Catálogo disponible tras ~${i}s"
    break
  fi
  sleep 1
done
echo "=== Petición tras la recuperación (esperado: 200 OK) ==="
call_orders

echo "Chaos test finalizado."
