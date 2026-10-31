import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL no está configurada")

# Render y otros proveedores usan postgres:// pero SQLAlchemy 1.4+ requiere postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Configuración de Connection Pool y resiliencia
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,       # Verifica que la conexión siga viva antes de usarla
    pool_recycle=1800,        # Recicla conexiones tras 30 min para evitar timeouts
    pool_timeout=30           # Espera máxima por una conexión del pool
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    """Generador de sesiones de base de datos con cierre garantizado."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
