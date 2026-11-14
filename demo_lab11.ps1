# ==============================================================================
# DEMOSTRACIÓN LAB 11: RATE LIMITING + CIRCUIT BREAKER + RETRY (CAMILA)
# ==============================================================================

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 1: Demostracion de Rate Limiter (Limite de peticiones por IP)" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

# Asegurar estado limpio
Invoke-RestMethod -Uri "http://127.0.0.1:8002/resilience/rate-limiter/reset" -Method Post | Out-Null

Write-Host "Enviando rafaga de 101 peticiones para alcanzar el limite..." -ForegroundColor White
$bloqueado = $false
for ($i = 1; $i -le 101; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -Method Get
    } catch {
        $codigo = $_.Exception.Response.StatusCode.value__
        $mensaje = $_.ErrorDetails.Message
        Write-Host "-> Peticion $i BLOQUEADA:" $codigo "-" $mensaje -ForegroundColor Red
        $bloqueado = $true
        break
    }
}

if (-not $bloqueado) {
    # Si la maquina es muy rapida o no alcanzo en el bucle, forzamos la peticion 101
    try {
        Invoke-RestMethod -Uri "http://127.0.0.1:8002/health" -Method Get
    } catch {
        Write-Host "-> Peticion BLOQUEADA:" $_.Exception.Response.StatusCode.value__ "-" $_.ErrorDetails.Message -ForegroundColor Red
    }
}

Write-Host "`nExplicacion: La API detecta que una misma direccion IP supero el limite permitido (100 peticiones en 60s) y la bloquea inmediatamente devolviendo codigo HTTP 429 Too Many Requests con la cabecera Retry-After: 60.`n" -ForegroundColor Gray

# Limpiar rate limiter para las siguientes pruebas
Invoke-RestMethod -Uri "http://127.0.0.1:8002/resilience/rate-limiter/reset" -Method Post | Out-Null


Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 2: Demostracion de Circuit Breaker (Estado CLOSED inicial)" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

$statusInicial = Invoke-RestMethod -Uri "http://127.0.0.1:8002/resilience/status" -Method Get
Write-Host "Estado actual del Circuit Breaker:" $statusInicial.circuit_breaker.state -ForegroundColor Green
$statusInicial.circuit_breaker | Format-List
Write-Host "Explicacion: El circuito inicia en estado CLOSED (cerrado), lo que permite que las solicitudes a servicios externos se ejecuten con normalidad.`n" -ForegroundColor Gray


Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 3: Demostracion de Fallo y Apertura del Circuito (Estado OPEN)" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

Write-Host "Simulando fallos consecutivos en el servicio externo (catalog-service)..." -ForegroundColor White
$tripResp = Invoke-RestMethod -Uri "http://127.0.0.1:8002/resilience/circuit-breaker/trip" -Method Post
Write-Host "-> Circuito forzado a:" $tripResp.state -ForegroundColor Red

try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8002/catalog/check/1" -Method Get
} catch {
    Write-Host "-> Respuesta del servicio:" $_.Exception.Response.StatusCode.value__ "-" $_.ErrorDetails.Message -ForegroundColor Red
}

Write-Host "`nExplicacion: Al detectar que el servicio externo fallo 5 veces seguidas, el Circuit Breaker cambia su estado a OPEN y bloquea de inmediato las llamadas devolviendo HTTP 503 Service Unavailable sin saturar la red ni esperar timeouts innecesarios.`n" -ForegroundColor Gray


Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 4: Recuperacion y Restablecimiento del Circuito" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

$resetResp = Invoke-RestMethod -Uri "http://127.0.0.1:8002/resilience/circuit-breaker/reset" -Method Post
Write-Host "-> Restableciendo circuito:" $resetResp.message -ForegroundColor Green

$statusFinal = Invoke-RestMethod -Uri "http://127.0.0.1:8002/resilience/status" -Method Get
Write-Host "Estado restablecido:" $statusFinal.circuit_breaker.state -ForegroundColor Green

Write-Host "`nExplicacion: Tras completarse el periodo de recuperacion (recovery_timeout de 60s) o restablecer el servicio, el circuito vuelve a CLOSED permitiendo nuevamente las operaciones normales.`n" -ForegroundColor Gray

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " ¡DEMOSTRACION DE LAB 11 COMPLETADA CON EXITO! " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
