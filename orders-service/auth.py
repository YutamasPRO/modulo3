import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import UserDB

# 2. Configurar la seguridad (LAB 10 - Taller 4)
SECRET_KEY = os.getenv("JWT_SECRET", "change-me-in-production-super-secret-key-123456789")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# 3. Configurar el cifrado de contraseñas y OAuth2
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# 4. Modelos de datos
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[str] = "user"


class UserInDB(BaseModel):
    id: Optional[int] = None
    email: str
    full_name: str
    role: str = "user"
    hashed_password: str


class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role: Optional[str] = "user"


class UserResponse(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# 5. Verificar las contraseñas
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# 6. Generar hashes de contraseñas
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# 7. Crear el token de acceso JWT (Con fecha UTC y duración unificada a 60 min)
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# 8. Identificar al usuario autenticado (Dependencia para validar token)
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> UserDB:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales o el token ha expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub") or payload.get("email")
        role: str = payload.get("role", "user")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email, role=role)
    except JWTError:
        raise credentials_exception

    user = db.query(UserDB).filter(UserDB.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    return user


# 9. Controlar los permisos según el rol (Jerarquía RBAC: user=1 < admin=2 < superadmin=3)
ROLE_HIERARCHY = {
    "user": 1,
    "admin": 2,
    "superadmin": 3
}


def require_role(required_role: str):
    """Fábrica de dependencias que restringe el acceso según el nivel jerárquico del rol."""
    def role_checker(current_user: UserDB = Depends(get_current_user)) -> UserDB:
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        required_level = ROLE_HIERARCHY.get(required_role, 99)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permisos insuficientes: se requiere rol '{required_role}' o superior"
            )
        return current_user
    return role_checker
