# Módulo 10 — Drift y observabilidad

## Objetivo

Cerrar el sistema con dos capas de "auto-vigilancia": detección de drift (señales que aparecen en el broker sin estar registradas) y observabilidad básica (métricas operativas de los servicios).

**Tiempo estimado**: 2-3 horas.

## Conceptos que vas a manejar

- **Drift**: cuando la realidad (lo que se publica) diverge de la fuente de verdad (el registro).
- **Promoción**: convertir una entrada de drift en una señal oficial registrada.
- **Métricas operativas**: contadores y latencias que indican cómo va el sistema.
- **Health checks**: endpoints que dicen "estoy vivo y funcionando".

## Lo que vas a montar

- `meta-ingestor`: servicio Python que detecta drift.
- Endpoints en `api-service` para revisar y gestionar drift.
- Página en el frontend para revisar drift pendiente.
- Health checks en cada servicio.

## Por qué importa el drift

En un sistema industrial real, los productores pueden cambiar sin que el equipo de plataforma se entere. Alguien añade un sensor nuevo a una turbina, configura el gateway para publicar al broker, y olvida registrar la señal en el sistema. Sin detección de drift:

- Los datos llegan al broker pero nadie los guarda.
- Los gráficos no los muestran porque el frontend no sabe que existen.
- Cuando alguien lo descubre 6 meses después, el dato lleva 6 meses perdiéndose.

Con detección de drift, el sistema avisa al admin: "alguien está publicando esta señal y no está registrada, ¿qué hacemos?".

## Paso a paso

### 1. meta-ingestor: estructura

```
services/meta-ingestor/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── config.py
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 2. Lógica del meta-ingestor (`app/main.py`)

```python
import asyncio
import json
import structlog
import asyncpg
import aiomqtt
from app.config import settings

log = structlog.get_logger()

async def is_registered(conn, topic: str) -> bool:
    """Comprueba si el topic '$meta/<n>' corresponde a una señal registrada."""
    # El topic registrado es 'measure/<n>' o 'events/<n>'.
    # Convertimos $meta a measure para buscar.
    parts = topic.split("/")
    if "$meta" not in parts:
        return False
    idx = parts.index("$meta")
    # Probamos primero como 'measure', luego como 'events'
    for ns in ("measure", "events", "$analytics"):
        candidate = "/".join(parts[:idx] + [ns] + parts[idx+1:])
        row = await conn.fetchrow(
            "SELECT 1 FROM signals WHERE topic = $1", candidate
        )
        if row:
            return True
    return False

async def already_in_drift(conn, topic: str) -> bool:
    row = await conn.fetchrow(
        "SELECT 1 FROM meta_drift WHERE topic = $1 AND status = 'pending'",
        topic
    )
    return row is not None

async def insert_drift(conn, topic: str, payload: dict):
    await conn.execute("""
        INSERT INTO meta_drift (topic, payload, status)
        VALUES ($1, $2, 'pending')
    """, topic, json.dumps(payload))

async def run():
    pg = await asyncpg.create_pool(
        host=settings.postgres_host, port=settings.postgres_port,
        user=settings.postgres_user, password=settings.postgres_password,
        database=settings.postgres_db,
    )
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                await client.subscribe("+/+/+/+/+/$meta/#")
                async for msg in client.messages:
                    topic = str(msg.topic)
                    if not msg.payload:
                        continue  # retained borrado
                    try:
                        payload = json.loads(msg.payload.decode())
                    except Exception:
                        continue
                    async with pg.acquire() as conn:
                        if await is_registered(conn, topic):
                            continue
                        if await already_in_drift(conn, topic):
                            continue
                        await insert_drift(conn, topic, payload)
                        log.warning("drift detected", topic=topic)
        except Exception as e:
            log.error("meta-ingestor crashed", error=str(e))
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run())
```

### 3. docker-compose

```yaml
  meta-ingestor:
    build: ./services/meta-ingestor
    container_name: meta-ingestor
    depends_on:
      - mqtt-broker
      - postgres
    environment:
      MQTT_HOST: mqtt-broker
      POSTGRES_HOST: postgres
      POSTGRES_USER: aeronorth
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: aeronorth
```

### 4. Endpoints de drift en api-service

`services/api-service/app/routers/drift.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db
from app.models.drift import MetaDrift

router = APIRouter(prefix="/api/v1/drift", tags=["drift"])

@router.get("")
async def list_drift(
    db: AsyncSession = Depends(get_db),
    status: str = "pending",
):
    result = await db.execute(
        select(MetaDrift).where(MetaDrift.status == status)
    )
    return result.scalars().all()

@router.post("/{id}/import")
async def import_drift(id: int, db: AsyncSession = Depends(get_db)):
    drift = await db.get(MetaDrift, id)
    if not drift:
        raise HTTPException(404)
    # Aquí: a partir de drift.payload (que tiene name, unit, datatype...),
    # crear una entrada en signals. Esta lógica debe inferir el asset_id
    # del topic, comprobar que existe, etc.
    # Para mantenerlo simple, este endpoint puede devolver al frontend
    # un "borrador" y dejar al usuario completar el formulario de creación
    # con los campos pre-rellenados.
    drift.status = "imported"
    await db.commit()
    return {"ok": True, "draft": drift.payload}

@router.post("/{id}/ignore")
async def ignore_drift(id: int, db: AsyncSession = Depends(get_db)):
    drift = await db.get(MetaDrift, id)
    if not drift:
        raise HTTPException(404)
    drift.status = "ignored"
    await db.commit()
    return {"ok": True}
```

### 5. Página de drift en el frontend

`src/pages/DriftReview.jsx`:

```javascript
import { useEffect, useState } from "react";

export function DriftReview() {
  const [items, setItems] = useState([]);

  const refresh = () =>
    fetch("http://localhost:8000/api/v1/drift?status=pending")
      .then(r => r.json())
      .then(setItems);

  useEffect(() => { refresh(); }, []);

  const importItem = async (id) => {
    const result = await fetch(`http://localhost:8000/api/v1/drift/${id}/import`, {
      method: "POST"
    }).then(r => r.json());
    // result.draft tiene los datos para pre-rellenar el formulario de signal
    alert(`Draft ready: ${JSON.stringify(result.draft)}`);
    refresh();
  };

  const ignoreItem = async (id) => {
    await fetch(`http://localhost:8000/api/v1/drift/${id}/ignore`, {
      method: "POST"
    });
    refresh();
  };

  return (
    <div>
      <h1>Pending drift ({items.length})</h1>
      <table>
        <thead>
          <tr>
            <th>Topic</th>
            <th>Detected at</th>
            <th>Payload</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {items.map(d => (
            <tr key={d.id}>
              <td>{d.topic}</td>
              <td>{new Date(d.detected_at).toLocaleString()}</td>
              <td><pre>{JSON.stringify(d.payload, null, 2)}</pre></td>
              <td>
                <button onClick={() => importItem(d.id)}>Import</button>
                <button onClick={() => ignoreItem(d.id)}>Ignore</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

### 6. Probar drift

Genera drift publicando un `$meta` "no registrado":

```bash
mosquitto_pub -h localhost -p 1883 \
  -t 'aeronorth/windfarm_north/sector_a/turbine_03/nacelle/$meta/humidity' \
  -m '{"name":"humidity","unit":"%RH","datatype":"float","criticality":"standard"}' \
  -r
```

A los pocos segundos, ve a `http://localhost:5173/drift`. Deberías ver la entrada de `humidity` esperando revisión.

### 7. Health checks

Añade a cada servicio Python un endpoint `/health` (en los que tienen FastAPI) o un comando bash que comprueba estado (en los que no).

`api-service`, `realtime-service`, `simulator`:

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

En `docker-compose.yml`:

```yaml
  api-service:
    # ...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Para los servicios sin HTTP (sync-service, event-ingestor, meta-ingestor, lkv-writer), un health check simple es comprobar que el proceso sigue vivo. Docker lo hace automáticamente — si el proceso principal muere, el contenedor reinicia.

### 8. Métricas básicas (opcional pero recomendado)

Añade `prometheus-client` a los servicios Python:

```python
from prometheus_client import Counter, Histogram, make_asgi_app

events_processed = Counter(
    "events_processed_total",
    "Number of events persisted",
    ["event_type", "severity"]
)

# En el handler:
events_processed.labels(event_type=type, severity=sev).inc()

# Mount /metrics endpoint:
app.mount("/metrics", make_asgi_app())
```

Si añades Prometheus + Grafana al docker-compose, tendrás dashboards de operación. Pero esto se sale del alcance de este curso base — lo dejamos como ejercicio avanzado.

## Lo que has aprendido

- Cómo detectar incoherencias entre el registro y la realidad del broker.
- Cómo gestionar el ciclo de vida del drift (pending → reviewed/imported/ignored).
- Cómo añadir health checks a servicios docker.
- Cómo el sistema puede vigilarse a sí mismo sin intervención manual.

## Comprobación final

- [ ] `meta-ingestor` corre y detecta `$meta` no registrados.
- [ ] La página de drift muestra las entradas pendientes.
- [ ] Puedes importar o ignorar drift desde el frontend.
- [ ] Los servicios tienen health checks que devuelven OK.

## Siguientes pasos (no incluidos en el curso base)

A partir de aquí, las extensiones naturales son:

- **Autenticación completa** con fastapi-users (registro, JWT en frontend).
- **Permisos y roles** (admin vs viewer; permisos por dashboard).
- **Comandos** (topic `cmd/...`): mandar órdenes desde el frontend al productor (encender/apagar, cambiar setpoint).
- **LLM como consumidor**: un servicio que usa la REST API y el WebSocket para responder preguntas en lenguaje natural ("¿cuál es la potencia media de la turbina 3 esta semana?").
- **Multi-site**: extender la jerarquía con varios `enterprise` o varios `site`.
- **Edge deployment**: meter el productor en un dispositivo edge separado del cloud.
- **Alertas activas**: notificaciones por email/Slack cuando se dispara una alarma crítica.

¡Enhorabuena por completar el curso!
