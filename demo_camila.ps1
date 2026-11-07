# ==============================================================================
# DEMOSTRACIÓN TALLER 4: AUTENTICACIÓN JWT + RBAC (CAMILA)
# ==============================================================================

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 1: Mostramos que la ruta /orders no es publica (requiere JWT)" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

try {
    $body = @{ space_id = 101; total_price = 50.0 } | ConvertTo-Json
    Invoke-RestMethod -Uri "http://127.0.0.1:8002/orders" -Method Post -Body $body -ContentType "application/json"
} catch {
    Write-Host "-> Error capturado:" $_.Exception.Response.StatusCode.value__ "-" $_.ErrorDetails.Message -ForegroundColor Red
    Write-Host "Explicacion: Intento crear una orden sin iniciar sesion, y me bota error 401 porque ya esta protegido con JWT.`n" -ForegroundColor Gray
}

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 2: Iniciamos sesion con usuario normal y obtenemos el Token JWT" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

$userLogin = @{ username = "camila.user@coworking.com"; password = "UserPass2026!" }
$tokenRes = Invoke-RestMethod -Uri "http://127.0.0.1:8002/auth/login" -Method Post -Body $userLogin
$userJwt = $tokenRes.access_token
Write-Host "-> Token generado exitosamente:" -ForegroundColor Green
Write-Host "$userJwt`n" -ForegroundColor DarkGreen
Write-Host "Explicacion: Inicio sesion con un usuario normal, se revisa la contrasena encriptada con bcrypt y me da el token JWT.`n" -ForegroundColor Gray

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 3: Creamos la orden con el Token Bearer incluido" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

$headers = @{ Authorization = "Bearer $userJwt" }
$orderData = @{ space_id = 999; total_price = 350.0 } | ConvertTo-Json
$createdOrder = Invoke-RestMethod -Uri "http://127.0.0.1:8002/orders" -Method Post -Body $orderData -Headers $headers -ContentType "application/json"
$createdOrder | Format-List
Write-Host "Explicacion: Le paso el token en la peticion y la valida, saca mi correo del token y crea la orden en la base de datos de PostgreSQL.`n" -ForegroundColor Gray

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " 4: Mostramos los permisos por rol (user vs admin)" -ForegroundColor Yellow
Write-Host "=================================================================" -ForegroundColor Cyan

Write-Host "[A] Intentando entrar con rol 'user' a la zona de admin:" -ForegroundColor White
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8002/admin/dashboard" -Method Get -Headers $headers
} catch {
    Write-Host "-> Respuesta:" $_.Exception.Response.StatusCode.value__ "-" $_.ErrorDetails.Message -ForegroundColor Red
    Write-Host "Explicacion: Intentamos entrar como usuario normal a la zona de admin y como tiene rol 'user' pues no lo deja entrar (403 Forbidden).`n" -ForegroundColor Gray
}

Write-Host "[B] Iniciando sesion como administrador y accediendo a la zona admin:" -ForegroundColor White
$adminLogin = @{ username = "camila.admin@coworking.com"; password = "AdminPass2026!" }
$adminToken = (Invoke-RestMethod -Uri "http://127.0.0.1:8002/auth/login" -Method Post -Body $adminLogin).access_token
$adminHeaders = @{ Authorization = "Bearer $adminToken" }

$adminResponse = Invoke-RestMethod -Uri "http://127.0.0.1:8002/admin/dashboard" -Method Get -Headers $adminHeaders
$adminResponse | ConvertTo-Json
Write-Host "`nExplicacion: Inicio sesion con el admin y si me deja entrar (200 OK) porque si tiene los permisos requeridos.`n" -ForegroundColor Gray

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host " ¡DEMOSTRACION COMPLETADA CON EXITO! " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Cyan
