# Informe de Chaos Engineering

> Los campos marcados con **[MEDIR]** deben completarse con los valores reales
> que arroje `./chaos-test.sh` y los `curl` del LAB 5 en tu máquina.

## Test 1: Caída de servicio dependiente

- **Escenario**: Se detiene el contenedor `catalog-service` (`docker-compose stop catalog-service`)
  mientras `orders-service` sigue activo y recibe `POST /orders`.
- **Impacto**: `orders-service` no puede validar el espacio ni obtener su precio, por lo que
  **no se pueden crear órdenes**. Responde `503 Catalog service unavailable` (error controlado,
  no un 500 ni un cuelgue). `GET /orders` y `/health` de orders siguen funcionando: la falla
  es parcial, no total. Es un acoplamiento temporal: la disponibilidad de orders depende de la de catalog.
- **Tiempo de detección**: **[MEDIR]** (valor `tiempo:` de la petición con catálogo caído).
  Como el nombre `catalog-service` deja de resolverse o la conexión se rechaza, el error es casi
  inmediato; en una caída "silenciosa" (red colgada) el techo sería el timeout configurado
  (`CATALOG_TIMEOUT`, 3 s por defecto).
- **Recuperación**: Automática al reiniciar el catálogo (`docker-compose start catalog-service`):
  no hace falta reiniciar orders-service porque cada petición abre una conexión nueva.
  Tiempo hasta volver a dar `200 OK`: **[MEDIR]**.

## Test 2: Cambio de contrato sin versionar

- **Escenario**: En `catalog-service` se renombra el campo `price_per_hour` a `hourly_rate`
  (en el modelo `Space` y en los datos) y se reconstruye solo ese servicio. `orders-service`
  no se toca ni se redespliega.
- **Impacto**: `POST /orders` falla con `500 Internal Server Error` (`KeyError: 'price_per_hour'`
  en los logs de orders-service). El catálogo responde `200` y su `/health` sigue "healthy",
  así que **ningún healthcheck detecta el problema**: la falla solo aparece en el flujo
  de negocio. Es una falla silenciosa y más difícil de diagnosticar que una caída.
- **Causa raíz**: Contrato implícito entre servicios. `orders-service` asume el nombre y la
  forma de los campos de `catalog-service`, pero no hay un contrato versionado ni pruebas
  que detecten el cambio incompatible (breaking change) antes del despliegue, y el consumidor
  accede al JSON sin validarlo.
- **Solución propuesta**:
  1. **Versionar el API** (`/v1/spaces`, `/v2/spaces`) y mantener la versión anterior hasta que
     todos los consumidores migren.
  2. **Cambios compatibles hacia atrás**: añadir `hourly_rate` conservando `price_per_hour`
     durante un periodo de deprecación (patrón expand/contract).
  3. **Contract testing** (p. ej. Pact o schemathesis) en CI: el consumidor publica lo que
     espera y el proveedor no puede desplegar si lo rompe.
  4. **Validar la respuesta en el consumidor** con un modelo Pydantic y devolver un
     `502 Bad Gateway` claro en lugar de un `500` por `KeyError`.
  5. Publicar y comunicar un esquema OpenAPI compartido.

## Comandos de debugging usados

- `docker-compose logs -f orders-service` → evidencia del `KeyError` (Test 2).
- `docker-compose ps` → estado de los contenedores (Test 1).
