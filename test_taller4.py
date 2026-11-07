"""Script de verificación integral de Taller 4:
LAB 10: Autenticación JWT + Control de Acceso Basado en Roles (RBAC).

Pruebas:
1. Verificación de tabla 'users' y migración Alembic en PostgreSQL.
2. Registro de usuario 'user' (/auth/register) -> 201 Created.
3. Registro de usuario 'admin' (/auth/register) -> 201 Created.
4. Intento de registro duplicado -> 400 Bad Request.
5. Login con credenciales incorrectas -> 401 Unauthorized.
6. Login exitoso (/auth/login) con OAuth2PasswordRequestForm -> Token JWT (HS256).
7. Verificación de perfil (/auth/me) con Token Bearer -> 200 OK (sin exponer password).
8. Acceso a /auth/me sin token -> 401 Unauthorized.
9. RBAC: Intento de acceso a /admin con rol 'user' -> 403 Forbidden.
10. RBAC: Acceso a /admin con rol 'admin' -> 200 OK.
"""
import os
import sys
import uuid

# Asegurar codificación utf-8 en terminales Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Cargar variables de entorno del servicio orders
sys.path.insert(0, os.path.abspath("orders-service"))
from dotenv import load_dotenv
load_dotenv("orders-service/.env")

from fastapi.testclient import TestClient
from database import engine, SessionLocal
from models import UserDB
from sqlalchemy import text
from main import app

client = TestClient(app)

print("=" * 65)
print("TEST TALLER 4: AUTENTICACIÓN JWT + CONTROL DE ACCESO BASADO EN ROLES")
print("=" * 65)

# --- 1. Verificación en Base de Datos ---
print("\n[PASO 1] Verificando tabla 'users' y migración en PostgreSQL...")
with engine.connect() as conn:
    version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    print(f"  [OK] Conexión a PostgreSQL activa. Alembic version: {version}")
    
    # Verificar que la tabla users existe
    columns = conn.execute(text("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'users'
        ORDER BY ordinal_position
    """)).fetchall()
    if columns:
        print(f"  [OK] Tabla 'users' detectada con {len(columns)} columnas:")
        for col in columns:
            print(f"       - {col[0]}: {col[1]}")
    else:
        print("  [ERROR] Tabla 'users' no encontrada!")
        sys.exit(1)

# Generar correos únicos para evitar conflictos en ejecuciones repetidas
test_id = uuid.uuid4().hex[:6]
user_email = f"user_{test_id}@coworking.test"
admin_email = f"admin_{test_id}@coworking.test"
password_comun = "Secret123*"

print(f"\n[INFO] Correos de prueba para este test:")
print(f"  - Usuario estándar: {user_email}")
print(f"  - Administrador:     {admin_email}")

# --- 2. Registro de Usuario Regular ---
print("\n[PASO 2] Probando POST /auth/register (rol 'user')...")
resp_reg_user = client.post("/auth/register", json={
    "email": user_email,
    "full_name": "Usuario Regular Test",
    "password": password_comun,
    "role": "user"
})
assert resp_reg_user.status_code == 201, f"Fallo registro usuario: {resp_reg_user.text}"
user_data = resp_reg_user.json()
print(f"  [OK] Usuario registrado con éxito (HTTP 201): ID={user_data.get('id')}, Role={user_data.get('role')}")
assert "hashed_password" not in user_data, "ALERTA: Se expuso hashed_password en UserResponse!"

# --- 3. Registro de Administrador ---
print("\n[PASO 3] Probando POST /auth/register (rol 'admin')...")
resp_reg_admin = client.post("/auth/register", json={
    "email": admin_email,
    "full_name": "Administrador Test",
    "password": password_comun,
    "role": "admin"
})
assert resp_reg_admin.status_code == 201, f"Fallo registro admin: {resp_reg_admin.text}"
admin_data = resp_reg_admin.json()
print(f"  [OK] Administrador registrado con éxito (HTTP 201): ID={admin_data.get('id')}, Role={admin_data.get('role')}")

# --- 4. Intento de Registro Duplicado ---
print("\n[PASO 4] Probando validación de email duplicado...")
resp_dup = client.post("/auth/register", json={
    "email": user_email,
    "full_name": "Duplicado",
    "password": "otra_clave",
    "role": "user"
})
assert resp_dup.status_code == 400, f"Se esperaba 400 pero se obtuvo {resp_dup.status_code}"
print(f"  [OK] Rechazado correctamente (HTTP 400): {resp_dup.json().get('detail')}")

# --- 5. Login con Password Incorrecta ---
print("\n[PASO 5] Probando POST /auth/login con credenciales erróneas...")
resp_bad_login = client.post("/auth/login", data={
    "username": user_email,
    "password": "PasswordInvalido"
})
assert resp_bad_login.status_code == 401, f"Se esperaba 401 pero se obtuvo {resp_bad_login.status_code}"
print(f"  [OK] Rechazado correctamente (HTTP 401): {resp_bad_login.json().get('detail')}")

# --- 6. Login Exitoso de Usuario Regular ---
print("\n[PASO 6] Obteniendo Token JWT para usuario regular...")
resp_login_user = client.post("/auth/login", data={
    "username": user_email,
    "password": password_comun
})
assert resp_login_user.status_code == 200, f"Fallo login usuario: {resp_login_user.text}"
user_token = resp_login_user.json()["access_token"]
print(f"  [OK] Login exitoso (HTTP 200). Access Token generado:")
print(f"       {user_token[:30]}...{user_token[-15:]}")

# --- 7. Login Exitoso de Administrador ---
print("\n[PASO 7] Obteniendo Token JWT para administrador...")
resp_login_admin = client.post("/auth/login", data={
    "username": admin_email,
    "password": password_comun
})
assert resp_login_admin.status_code == 200, f"Fallo login admin: {resp_login_admin.text}"
admin_token = resp_login_admin.json()["access_token"]
print(f"  [OK] Login admin exitoso (HTTP 200). Access Token generado:")
print(f"       {admin_token[:30]}...{admin_token[-15:]}")

# --- 8. Acceso a /auth/me con Token ---
print("\n[PASO 8] Probando GET /auth/me con Bearer Token...")
resp_me = client.get("/auth/me", headers={"Authorization": f"Bearer {user_token}"})
assert resp_me.status_code == 200, f"Fallo /auth/me: {resp_me.text}"
me_data = resp_me.json()
print(f"  [OK] Perfil validado (HTTP 200): {me_data.get('email')} | Rol: {me_data.get('role')}")
assert me_data.get("email") == user_email

# --- 9. Acceso a /auth/me sin Token ---
print("\n[PASO 9] Probando GET /auth/me sin cabecera de autenticación...")
resp_me_unauth = client.get("/auth/me")
assert resp_me_unauth.status_code == 401, f"Se esperaba 401 pero se obtuvo {resp_me_unauth.status_code}"
print(f"  [OK] Rechazado correctamente (HTTP 401)")

# --- 10. RBAC: Usuario intentando acceder a /admin ---
print("\n[PASO 10] Probando RBAC: Usuario regular intentando acceder a /admin...")
resp_admin_forbidden = client.get("/admin", headers={"Authorization": f"Bearer {user_token}"})
assert resp_admin_forbidden.status_code == 403, f"Se esperaba 403 pero se obtuvo {resp_admin_forbidden.status_code}: {resp_admin_forbidden.text}"
print(f"  [OK] Acceso denegado correctamente (HTTP 403 Forbidden):")
print(f"       Detalle: {resp_admin_forbidden.json().get('detail')}")

# --- 11. RBAC: Administrador accediendo a /admin ---
print("\n[PASO 11] Probando RBAC: Administrador accediendo a /admin...")
resp_admin_ok = client.get("/admin", headers={"Authorization": f"Bearer {admin_token}"})
assert resp_admin_ok.status_code == 200, f"Fallo acceso admin: {resp_admin_ok.text}"
print(f"  [OK] Acceso autorizado correctamente (HTTP 200 OK):")
print(f"       Respuesta: {resp_admin_ok.json()}")

print("\n" + "=" * 65)
print("¡TODAS LAS PRUEBAS DE TALLER 4 COMPLETADAS CON ÉXITO! (10/10)")
print("=" * 65)

