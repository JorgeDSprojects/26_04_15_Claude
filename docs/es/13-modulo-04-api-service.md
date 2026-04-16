# Módulo 4 — El registro UNS y el api-service

## Objetivo

Construir el corazón administrativo del sistema: el registro de señales en PostgreSQL y la API REST que lo expone. Al terminar, podrás dar de alta activos y señales desde un panel de administración web (SQLAdmin) y consultarlos vía API REST.

**Tiempo estimado**: 3-4 horas.

## Conceptos que vas a manejar

- **PostgreSQL** como fuente de verdad del registro.
- **SQLAlchemy 2.x async** para mapeo objeto-relacional asíncrono.
- **Alembic** para migraciones de esquema.
- **FastAPI** como framework HTTP async.
- **Pydantic v2** para validación de schemas.
- **fastapi-users** para autenticación con JWT.
- **SQLAdmin** para un panel admin tipo Django.

## Lo que vas a montar

Añadir al `docker-compose.yml`:
- `postgres`: BBDD del registro (separada de TimescaleDB).
- `api-service`: FastAPI con todo lo de arriba.

## Por qué dos Postgres separados

Una pregunta legítima: si TimescaleDB es Postgres con una extensión, ¿por qué no usar una única instancia?

**Razón principal**: separación de responsabilidades. El registro es OLTP (cientos de filas, escrituras puntuales). TimescaleDB es time-series (millones de filas, escrituras masivas). Las características de tuning son distintas: shared_buffers, WAL config, vacuum policies. Mezclarlos hace difícil optimizar uno sin afectar al otro.

**Razón secundaria**: aislamiento operativo. Si TimescaleDB se llena de datos y necesita mantenimiento, no quieres que tu registro de señales se vea afectado.

En desarrollo local con poco volumen es exagerado, pero los hábitos se forman desde el principio. En producción se va a agradecer.

## Paso a paso

### 1. Postgres del registro en docker-compose

```yaml
  postgres:
    image: postgres:16
    container_name: postgres
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: aeronorth
      POSTGRES_USER: aeronorth
      POSTGRES_PASSWORD: changeme
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  # ...
  postgres-data:
```

### 2. Estructura del api-service

```
services/api-service/
├── app/
│   ├── __init__.py
│   ├── main.py                # App factory, lifespan
│   ├── config.py              # Settings
│   ├── db.py                  # Engine, session
│   ├── models/                # SQLAlchemy models
│   │   ├── __init__.py
│   │   ├── base.py            # Declarative base
│   │   ├── asset.py
│   │   ├── signal.py
│   │   └── user.py
│   ├── schemas/               # Pydantic
│   │   ├── asset.py
│   │   └── signal.py
│   ├── routers/               # FastAPI routers
│   │   ├── assets.py
│   │   └── signals.py
│   ├── services/              # Business logic
│   │   └── topic_builder.py
│   ├── auth/                  # fastapi-users wiring
│   └── admin/                 # SQLAdmin views
├── alembic/
│   ├── versions/
│   ├── env.py
│   └── script.py.mako
├── alembic.ini
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 3. Dependencias (`pyproject.toml`)

```toml
[project]
name = "api-service"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "fastapi-users[sqlalchemy]>=13.0",
    "sqladmin>=0.18",
    "structlog>=24.0",
    "httpx>=0.27",
]
```

### 4. Configuración (`app/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str
    api_cors_origins: list[str] = ["http://localhost:5173"]

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "aeronorth"
    postgres_user: str
    postgres_password: str

    timescale_host: str = "timescaledb"
    timescale_port: int = 5432   # ¡5432, no 5433! 5433 es el host port
    timescale_db: str = "metrics"
    timescale_user: str
    timescale_password: str

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def timescale_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.timescale_user}:{self.timescale_password}"
            f"@{self.timescale_host}:{self.timescale_port}/{self.timescale_db}"
        )

settings = Settings()
```

**Nota importante sobre puertos**: en docker-compose, los servicios se hablan entre sí por su puerto interno (5432 para Postgres). El puerto 5433 que vimos en el módulo 3 es solo el mapeo al host para que TÚ puedas conectarte desde fuera. Telegraf y api-service hablan a `timescaledb:5432` dentro de la red Docker.

### 5. Modelos SQLAlchemy

`app/models/base.py`:
```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

`app/models/asset.py`:
```python
from datetime import datetime
from sqlalchemy import String, ForeignKey, JSON, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

class AssetType(Base):
    __tablename__ = "asset_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    isa95_level: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)

class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("parent_id", "code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"))
    asset_type_id: Mapped[int] = mapped_column(ForeignKey("asset_types.id"))
    code: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    children: Mapped[list["Asset"]] = relationship(
        "Asset", remote_side=[id], backref="parent"
    )
```

`app/models/signal.py`: similar pero con todos los campos de la tabla `signals` que vimos en `02-data-model.md`.

### 6. Migración inicial con Alembic

```bash
docker compose run --rm api-service alembic init alembic
docker compose run --rm api-service alembic revision --autogenerate -m "initial schema"
docker compose run --rm api-service alembic upgrade head
```

Edita la migración generada para añadir el trigger de LISTEN/NOTIFY (no se autogenera, hay que añadirlo a mano):

```python
# En el upgrade() de la migración:
op.execute("""
    CREATE OR REPLACE FUNCTION notify_signal_change()
    RETURNS TRIGGER AS $$
    BEGIN
        PERFORM pg_notify('signals_changed', json_build_object(
            'op', TG_OP, 'id', COALESCE(NEW.id, OLD.id)
        )::text);
        RETURN COALESCE(NEW, OLD);
    END;
    $$ LANGUAGE plpgsql;

    CREATE TRIGGER signals_notify
    AFTER INSERT OR UPDATE OR DELETE ON signals
    FOR EACH ROW EXECUTE FUNCTION notify_signal_change();
""")
```

### 7. Routers REST básicos

`app/routers/signals.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db
from app.schemas.signal import SignalCreate, SignalResponse
from app.services.topic_builder import compute_topic
from app.models.signal import Signal
from app.models.asset import Asset
from sqlalchemy import select

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])

@router.post("", response_model=SignalResponse, status_code=201)
async def create_signal(payload: SignalCreate, db: AsyncSession = Depends(get_db)):
    asset = await db.get(Asset, payload.asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    topic = compute_topic(asset.path, payload.signal_type_name, payload.name)
    signal = Signal(**payload.model_dump(), topic=topic)
    db.add(signal)
    await db.commit()
    await db.refresh(signal)
    return signal

@router.get("", response_model=list[SignalResponse])
async def list_signals(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Signal))
    return result.scalars().all()
```

### 8. SQLAdmin

```python
from sqladmin import Admin, ModelView
from app.models.asset import Asset
from app.models.signal import Signal

class AssetAdmin(ModelView, model=Asset):
    column_list = [Asset.id, Asset.code, Asset.display_name, Asset.path]
    column_searchable_list = [Asset.code, Asset.path]

class SignalAdmin(ModelView, model=Signal):
    column_list = [Signal.id, Signal.name, Signal.unit, Signal.criticality, Signal.topic]
    column_searchable_list = [Signal.name, Signal.topic]

# En main.py:
admin = Admin(app, engine)
admin.add_view(AssetAdmin)
admin.add_view(SignalAdmin)
```

### 9. App factory (`app/main.py`)

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.config import settings
from app.db import engine
from app.routers import signals, assets

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    yield
    # shutdown
    await engine.dispose()

app = FastAPI(title="AeroNorth UNS API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.api_cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(assets.router)
app.include_router(signals.router)

# SQLAdmin mount aquí
```

### 10. Arranca y prueba

```bash
docker compose up -d --build api-service
```

- Abre `http://localhost:8000/docs` → OpenAPI UI generada por FastAPI.
- Abre `http://localhost:8000/admin` → panel SQLAdmin.

Da de alta:
1. Un `asset_type` (`enterprise`, `wind_farm`, `wind_turbine`, etc.)
2. Activos en orden jerárquico (primero `aeronorth`, luego `windfarm_north`, etc.)
3. Una señal de prueba.

Verifica vía API:
```bash
curl http://localhost:8000/api/v1/signals
```

## Lo que has aprendido

- Cómo estructurar un servicio FastAPI con SQLAlchemy async.
- Cómo usar Alembic para versionar migraciones.
- Cómo crear endpoints REST con validación Pydantic.
- Cómo añadir un panel admin con SQLAdmin.
- Cómo añadir triggers SQL en migraciones Alembic.

## Lo que NO has hecho todavía

- Conectar el registro al broker MQTT (eso es el módulo 5).
- Auth real (lo dejamos para después o lo añades como ejercicio).
- Consultas históricas a TimescaleDB.

## Comprobación final

- [ ] `api-service` corre y `/docs` responde.
- [ ] Puedes crear y listar assets desde `/admin`.
- [ ] Puedes crear señales y se autocomputa el topic.
- [ ] El trigger `signals_notify` está creado en Postgres.

## Siguiente módulo

[Módulo 5 — El sync-service y LISTEN/NOTIFY](14-modulo-05-sync-service.md)
