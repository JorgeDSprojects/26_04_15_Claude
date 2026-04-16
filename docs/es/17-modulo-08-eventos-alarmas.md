# Módulo 8 — Eventos, alarmas y QoS 1

## Objetivo

Construir el camino completo de los eventos críticos: del simulador al broker (con QoS 1), del broker al `event-ingestor` (con sesión persistente), y del broker al navegador (con widget de alarmas). Demostrar que el sistema no pierde eventos ni siquiera cuando un consumidor se cae.

**Tiempo estimado**: 2-3 horas.

## Conceptos que vas a manejar

- **QoS 1**: at-least-once delivery, con ACK del receptor.
- **Sesión persistente**: el broker guarda mensajes para clientes desconectados.
- **Idempotencia**: el consumidor está preparado para recibir duplicados.
- **Acknowledgment**: marcar una alarma como "vista" por un usuario.
- **Inyección manual de eventos** desde el frontend (para demos).

## Lo que vas a montar

- `event-ingestor`: servicio Python que persiste eventos MQTT en Postgres.
- Endpoint en el simulador: `POST /trigger-event` para inyectar eventos manualmente.
- Widget `AlarmList` en el frontend.

## Por qué los eventos son distintos

La telemetría informativa (`measure`) es continua: si pierdes una muestra, en 10 segundos llega la siguiente y normalmente da igual. Los eventos son **discretos**: una parada de emergencia ocurre una vez. Si la pierdes, no vuelve a "ocurrir" en 10 segundos. Necesitas garantía de entrega.

Por eso:
- Topic separado: `events/<event_type>` en lugar de `measure/<signal>`.
- QoS 1 obligatorio en publicador y consumidor.
- Sesión persistente en el `event-ingestor` para que el broker le guarde mensajes si está caído.
- Tabla relacional en Postgres (no time-series) porque tienen estructura: `acknowledged_at`, `acknowledged_by`.

## Paso a paso

### 1. event-ingestor: estructura

```
services/event-ingestor/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   └── topic_parser.py    # extrae asset_path del topic
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 2. Dependencias

```toml
[project]
dependencies = [
    "asyncpg>=0.29",
    "aiomqtt>=2.3",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
]
```

### 3. Topic parser (`app/topic_parser.py`)

```python
def parse_event_topic(topic: str) -> tuple[str, str]:
    """
    Devuelve (asset_path, event_type) a partir de un topic events.

    Ejemplo:
      'aeronorth/windfarm_north/sector_a/turbine_03/controller/events/emergency_stop'
      → ('aeronorth/windfarm_north/sector_a/turbine_03/controller', 'emergency_stop')
    """
    parts = topic.split("/")
    if "events" not in parts:
        raise ValueError(f"not an event topic: {topic}")
    idx = parts.index("events")
    asset_path = "/".join(parts[:idx])
    event_type = "/".join(parts[idx + 1:])
    return asset_path, event_type
```

### 4. Main (`app/main.py`)

```python
import asyncio
import json
import structlog
import asyncpg
import aiomqtt
from app.config import settings
from app.topic_parser import parse_event_topic

log = structlog.get_logger()

async def lookup_asset_id(conn, asset_path: str) -> int | None:
    row = await conn.fetchrow(
        "SELECT id FROM assets WHERE path = $1", asset_path
    )
    return row["id"] if row else None

async def insert_event(conn, asset_id, event_type, severity, payload, occurred_at):
    await conn.execute("""
        INSERT INTO events (asset_id, event_type, severity, payload, occurred_at)
        VALUES ($1, $2, $3, $4, to_timestamp($5 / 1000.0))
    """, asset_id, event_type, severity, json.dumps(payload), occurred_at)

async def run():
    pg = await asyncpg.create_pool(
        host=settings.postgres_host, port=settings.postgres_port,
        user=settings.postgres_user, password=settings.postgres_password,
        database=settings.postgres_db,
    )

    while True:
        try:
            # client_id estable + clean_session=False = sesión persistente
            async with aiomqtt.Client(
                settings.mqtt_host,
                settings.mqtt_port,
                client_id="event-ingestor",
                clean_session=False,
            ) as client:
                await client.subscribe("+/+/+/+/+/events/#", qos=1)
                log.info("event-ingestor subscribed")

                async for msg in client.messages:
                    try:
                        topic = str(msg.topic)
                        payload = json.loads(msg.payload.decode())
                        asset_path, event_type = parse_event_topic(topic)
                    except Exception as e:
                        log.warning("malformed event", topic=str(msg.topic), error=str(e))
                        continue

                    async with pg.acquire() as conn:
                        asset_id = await lookup_asset_id(conn, asset_path)
                        if not asset_id:
                            log.warning("unknown asset", path=asset_path)
                            continue
                        await insert_event(
                            conn,
                            asset_id,
                            payload.get("event_type", event_type),
                            payload.get("severity", "info"),
                            payload.get("data", {}),
                            payload.get("ts", 0),
                        )
                        log.info("event persisted", type=event_type, asset=asset_path)
        except Exception as e:
            log.error("event-ingestor crashed", error=str(e))
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run())
```

**Importante**: el `client_id="event-ingestor"` y `clean_session=False` activan la sesión persistente del broker. Esto significa que si el `event-ingestor` se desconecta, EMQX guarda los mensajes destinados a él hasta que vuelva.

### 5. Añade event-ingestor al docker-compose

```yaml
  event-ingestor:
    build: ./services/event-ingestor
    container_name: event-ingestor
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

### 6. Inyección manual de eventos desde el simulador

Modifica `services/simulator/app/main.py` añadiendo un pequeño endpoint HTTP:

```python
from fastapi import FastAPI
import asyncio
import json
import time
import aiomqtt
from app.config import settings

app = FastAPI()

@app.post("/inject-event")
async def inject_event(data: dict):
    """
    Body esperado:
    {
      "asset_path": "aeronorth/windfarm_north/sector_a/turbine_02/controller",
      "event_type": "emergency_stop",
      "severity": "critical",
      "data": {"trigger": "manual"}
    }
    """
    topic = f"{data['asset_path']}/events/{data['event_type']}"
    payload = json.dumps({
        "event_type": data["event_type"],
        "severity": data.get("severity", "info"),
        "ts": int(time.time() * 1000),
        "data": data.get("data", {}),
    }).encode()
    async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as c:
        await c.publish(topic, payload, qos=1)
    return {"ok": True, "topic": topic}
```

Necesitarás separar el simulador en dos bucles concurrentes (el de CSV + el de FastAPI). La forma más limpia: mover el bucle CSV a una task de fondo en el lifespan de FastAPI.

Expón el puerto en docker-compose:

```yaml
  simulator:
    # ...
    ports:
      - "8002:8002"
    command: uvicorn app.main:app --host 0.0.0.0 --port 8002
```

### 7. Prueba inyección y persistencia

```bash
# Genera un evento manualmente
curl -X POST http://localhost:8002/inject-event \
  -H "Content-Type: application/json" \
  -d '{
    "asset_path": "aeronorth/windfarm_north/sector_a/turbine_03/controller",
    "event_type": "emergency_stop",
    "severity": "critical",
    "data": {"trigger": "test_manual"}
  }'

# Comprueba que se ha persistido
docker compose exec postgres psql -U aeronorth -d aeronorth \
  -c "SELECT id, event_type, severity, occurred_at FROM events ORDER BY id DESC LIMIT 5;"
```

### 8. La prueba que demuestra QoS 1 + sesión persistente

Esta es la demo "wow" del módulo:

```bash
# 1. Para el event-ingestor
docker compose stop event-ingestor

# 2. Inyecta 5 eventos
for i in 1 2 3 4 5; do
  curl -X POST http://localhost:8002/inject-event \
    -H "Content-Type: application/json" \
    -d "{
      \"asset_path\": \"aeronorth/windfarm_north/sector_a/turbine_03/controller\",
      \"event_type\": \"test_event_$i\",
      \"severity\": \"warning\",
      \"data\": {\"index\": $i}
    }"
done

# 3. Confirma que NO están en Postgres aún
docker compose exec postgres psql -U aeronorth -d aeronorth \
  -c "SELECT COUNT(*) FROM events WHERE event_type LIKE 'test_event_%';"
# debería ser 0

# 4. Levanta el event-ingestor
docker compose start event-ingestor
sleep 5

# 5. Comprueba que ahora SÍ están
docker compose exec postgres psql -U aeronorth -d aeronorth \
  -c "SELECT event_type FROM events WHERE event_type LIKE 'test_event_%' ORDER BY event_type;"
# deberían estar los 5
```

Esto demuestra que el broker guardó los 5 mensajes mientras el ingestor estaba caído, y se los entregó cuando volvió. Cero pérdida de datos.

### 9. Endpoint de eventos en api-service

Añade a `services/api-service/app/routers/events.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db
from app.models.event import Event

router = APIRouter(prefix="/api/v1/events", tags=["events"])

@router.get("")
async def list_events(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(100, le=1000),
    asset_id: int | None = None,
    acknowledged: bool | None = None,
):
    stmt = select(Event).order_by(desc(Event.occurred_at)).limit(limit)
    if asset_id:
        stmt = stmt.where(Event.asset_id == asset_id)
    if acknowledged is True:
        stmt = stmt.where(Event.acknowledged_at.is_not(None))
    elif acknowledged is False:
        stmt = stmt.where(Event.acknowledged_at.is_(None))
    result = await db.execute(stmt)
    return result.scalars().all()

@router.post("/{event_id}/acknowledge")
async def acknowledge(event_id: int, db: AsyncSession = Depends(get_db)):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404)
    event.acknowledged_at = datetime.utcnow()
    await db.commit()
    return event
```

### 10. Widget AlarmList en el frontend

```javascript
// src/components/AlarmList.jsx
import { useEffect, useState } from "react";

export function AlarmList() {
  const [alarms, setAlarms] = useState([]);

  useEffect(() => {
    const fetchAlarms = () =>
      fetch("http://localhost:8000/api/v1/events?acknowledged=false&limit=20")
        .then(r => r.json())
        .then(setAlarms);
    fetchAlarms();
    const id = setInterval(fetchAlarms, 5000);
    return () => clearInterval(id);
  }, []);

  const ack = async (id) => {
    await fetch(`http://localhost:8000/api/v1/events/${id}/acknowledge`, {
      method: "POST",
    });
    setAlarms(alarms.filter(a => a.id !== id));
  };

  return (
    <div>
      <h2>Active Alarms ({alarms.length})</h2>
      <ul>
        {alarms.map(a => (
          <li key={a.id}>
            <strong>[{a.severity}]</strong> {a.event_type} —
            asset {a.asset_id} — {new Date(a.occurred_at).toLocaleString()}
            <button onClick={() => ack(a.id)}>Ack</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

Combínalo con el LiveChart en App.jsx.

## Lo que has aprendido

- Cómo configurar QoS 1 + sesión persistente para garantía end-to-end.
- Cómo demostrar empíricamente la garantía tirando un servicio.
- Cómo separar la lógica de eventos (relacional, OLTP) de la telemetría (time-series).
- Cómo construir un widget de alarmas con polling REST + acknowledge.

## Comprobación final

- [ ] Los eventos inyectados aparecen en la tabla `events` de Postgres.
- [ ] Si paras el `event-ingestor` y disparas eventos, al volver se procesan todos.
- [ ] El widget de alarmas muestra y permite reconocer eventos.
- [ ] Reconocer un evento lo hace desaparecer del widget.

## Siguiente módulo

[Módulo 9 — Dashboards dinámicos con GridStack](18-modulo-09-dashboards.md)
