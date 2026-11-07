@echo off
chcp 65001 >nul
echo ========================================================
echo  INICIANDO MICROSERVICIOS DE COWORKING (FASTAPI)
echo ========================================================

echo 1. Cerrando instancias previas si existen...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 :8002 :8003"') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo 2. Iniciando Catalog Service en http://localhost:8001...
start "Catalog Service (8001)" /b python -m uvicorn main:app --app-dir catalog-service --port 8001

echo 3. Iniciando Orders Service (JWT + RBAC + DB) en http://localhost:8002...
start "Orders Service (8002)" /b python -m uvicorn main:app --app-dir orders-service --port 8002

echo 4. Iniciando Analytics Service (MongoDB) en http://localhost:8003...
start "Analytics Service (8003)" /b python -m uvicorn main:app --app-dir analytics-service --port 8003

timeout /t 3 /nobreak >nul

echo.
echo ========================================================
echo  ¡TODOS LOS SERVICIOS ESTAN ACTIVOS Y CORRIENDO!
echo ========================================================
echo  - Swagger Catalog:   http://localhost:8001/docs
echo  - Swagger Orders:    http://localhost:8002/docs  <-- (Taller 4: /auth y /admin)
echo  - Swagger Analytics: http://localhost:8003/docs
echo ========================================================
echo.
echo Abriendo Swagger en el navegador...
start http://localhost:8002/docs
start http://localhost:8003/docs
pause

