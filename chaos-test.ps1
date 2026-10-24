# LAB 4 - Chaos Engineering (version PowerShell para Windows)
# Uso:  .\chaos-test.ps1
# Si Windows bloquea el script:  powershell -ExecutionPolicy Bypass -File .\chaos-test.ps1

$OrdersUrl = "http://localhost:8002/orders?space_id=1&user_email=chaos@test.com&hours=2"

# Soporta "docker compose" (v2, Docker Desktop) y "docker-compose" (v1)
$useV1 = $false
if (Get-Command docker-compose -ErrorAction SilentlyContinue) { $useV1 = $true }
function Invoke-DC {
    if ($useV1) { & docker-compose @args } else { & docker compose @args }
}

function Call-Orders {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $code = 0
    $body = ""
    try {
        $r = Invoke-WebRequest -Uri $OrdersUrl -Method POST -UseBasicParsing -TimeoutSec 15
        $code = [int]$r.StatusCode
        $body = $r.Content
    } catch {
        if ($_.Exception.Response) {
            $code = [int]$_.Exception.Response.StatusCode
            if ($_.ErrorDetails -and $_.ErrorDetails.Message) {
                $body = $_.ErrorDetails.Message
            } else {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                $body = $reader.ReadToEnd()
            }
        } else {
            $code = 0
            $body = $_.Exception.Message
        }
    }
    $sw.Stop()
    Write-Host ("HTTP {0} | tiempo: {1:N3}s" -f $code, $sw.Elapsed.TotalSeconds)
    Write-Host "Respuesta: $body"
    Write-Host ""
}

Write-Host "=== 1. Estado normal (esperado: 200 OK) ===" -ForegroundColor Cyan
Call-Orders

Write-Host "=== 2. Apagando catalog-service ===" -ForegroundColor Cyan
Invoke-DC stop catalog-service
Start-Sleep -Seconds 2
Write-Host "=== Peticion con catalogo caido (esperado: 503 Catalog service unavailable) ===" -ForegroundColor Cyan
Call-Orders

Write-Host "=== 3. Recuperando catalog-service ===" -ForegroundColor Cyan
Invoke-DC start catalog-service
Write-Host "Esperando a que el catalogo este listo..."
$sw = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 1; $i -le 30; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:8001/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        Write-Host ("Catalogo disponible tras {0:N1}s" -f $sw.Elapsed.TotalSeconds)
        break
    } catch { Start-Sleep -Seconds 1 }
}
Write-Host "=== Peticion tras la recuperacion (esperado: 200 OK) ===" -ForegroundColor Cyan
Call-Orders

Write-Host "Chaos test finalizado." -ForegroundColor Green
