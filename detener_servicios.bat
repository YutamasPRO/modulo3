@echo off
chcp 65001 >nul
echo Deteniendo todos los servicios en puertos 8001, 8002 y 8003...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8001 :8002 :8003"') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo Servicios detenidos exitosamente.
pause
