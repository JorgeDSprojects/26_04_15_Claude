# Módulo 5 — El sync-service y LISTEN/NOTIFY

## Objetivo

Cerrar el círculo entre el registro de señales (Postgres) y el broker MQTT. Construir un servicio que reaccione automáticamente a los cambios en Postgres y publique los `$meta` retenidos correspondientes en el broker.

Al terminar, podrás dar de alta una señal en SQLAdmin y ver inmediatamente con `mosquitto_sub` cómo aparece su `$meta` retenido en el broker.

**Tiempo estimado**: 1-2 horas.

## Conceptos que vas a manejar

- **LISTEN/NOTIFY de PostgreSQL**: notificaciones en tiempo real desde la BBDD.
- **Mensaje retenido**: el broker guarda el último mensaje y lo entrega a nuevos suscriptores.
- **Reconciliación**: comparar estado actual vs estado deseado y aplicar las diferencias.
- **Patrón "fuente de verdad + espejo"**: SQL es maestro, MQTT es esclavo.

## Lo que vas a montar

Añadir al `docker-compose.yml`:
- `sync-service`: servicio Python que escucha cambios en Postgres y publica al broker.

## El patrón

```
Tú creas señal en SQLAdmin
    ↓
api-service hace INSERT
    ↓
Postgres trigger emite NOTIFY signals_changed
    ↓
sync-service recibe la notificación
    ↓
sync-service consulta la fila completa en Postgres
    ↓
sync-service publica $meta retenido en MQTT
    ↓
EMQX guarda el retained
    ↓
Cualquier consumidor que se suscriba en el futuro
recibe el $meta inmediatamente, sin esperar
```

Latencia total: pocos milisegundos. Sin polling, sin colas externas.

## Por qué LISTEN/NOTIFY y no Redis pub/sub o Kafka

Tres opciones para "reaccionar a cambios en Postgres":

1. **Polling**: el sync-service consulta cada N segundos buscando cambios. Feo, lento, ineficiente.
2. **Cola externa** (Redis pub/sub, Kafka, RabbitMQ): el api-service publica un evento. Funciona, pero añade un componente más y otro punto de fallo.
3. **LISTEN/NOTIFY de Postgres**: nativo de la BBDD. Cero infraestructura adicional. Latencia microsegundos.

Para nuestro caso (un solo escritor: api-service; un solo lector: sync-service; baja frecuencia: las señales se dan de alta a mano, no a 1000 por segundo), LISTEN/NOTIFY es perfecto.

## Paso a paso

### 1. Estructura del servicio

```
services/sync-service/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── reconciler.py     # Lógica de "qué publicar"
│   └── notify_listener.py # Lógica de "escuchar Postgres"
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

### 3. Listener de Postgres (`app/notify_listener.py`)

```python
import asyncio
import json
import asyncpg
import structlog
from app.config import settings

log = structlog.get_logger()

async def listen_for_changes(callback):
    """Conecta a Postgres y escucha NOTIFY signals_changed indefinidamente."""
    conn = await asyncpg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )
    log.info("connected to postgres, listening on signals_changed")

    async def _on_notify(connection, pid, channel, payload):
        try:
            data = json.loads(payload)
            await callback(data)
        except Exception as e:
            log.exception("error in callback", error=str(e))

    await conn.add_listener("signals_changed", _on_notify)
    await conn.add_listener("assets_changed", _on_notify)

    # Mantener la conexión viva indefinidamente
    while True:
        await asyncio.sleep(60)
```

### 4. Reconciliador (`app/reconciler.py`)

```python
import json
import structlog
import asyncpg
import aiomqtt
from app.config import settings

log = structlog.get_logger()

async def fetch_signal(conn, signal_id: int) -> dict | None:
    """Lee la fila completa de la señal con join al asset."""
    row = await conn.fetchrow("""
        SELECT
            s.id, s.name, s.display_name, s.unit, s.datatype,
            s.criticality, s.topic, s.enabled, s.min_value, s.max_value,
            s.metadata, s.updated_at,
            a.path AS asset_path, a.display_name AS asset_display_name,
            st.name AS signal_type_name
        FROM signals s
        JOIN assets a ON s.asset_id = a.id
        JOIN signal_types st ON s.signal_type_id = st.id
        WHERE s.id = $1
    """, signal_id)
    return dict(row) if row else None

def build_meta_topic(signal: dict) -> str:
    """Convierte el topic 'measure' o 'events' a '$meta'."""
    return f"{signal['asset_path']}/$meta/{signal['name']}"

def build_meta_payload(signal: dict) -> bytes:
    payload = {
        "signal_id": signal["id"],
        "name": signal["name"],
        "display_name": signal["display_name"],
        "unit": signal["unit"],
        "datatype": signal["datatype"],
        "criticality": signal["criticality"],
        "min_value": signal.get("min_value"),
        "max_value": signal.get("max_value"),
        "enabled": signal["enabled"],
        "asset_path": signal["asset_path"],
        "asset_display_name": signal["asset_display_name"],
        "updated_at": signal["updated_at"].isoformat(),
    }
    return json.dumps(payload).encode()

async def publish_meta(mqtt_client, signal: dict):
    topic = build_meta_topic(signal)
    payload = build_meta_payload(signal)
    await mqtt_client.publish(topic, payload, qos=1, retain=True)
    log.info("$meta published", topic=topic)

async def delete_meta(mqtt_client, topic: str):
    """Borrar un retained: publicar payload vacío con retain=true."""
    await mqtt_client.publish(topic, b"", qos=1, retain=True)
    log.info("$meta deleted", topic=topic)

async def reconcile_all(pg_conn, mqtt_client):
    """En el arranque: publica todos los $meta para asegurar consistencia."""
    rows = await pg_conn.fetch("""
        SELECT s.id FROM signals s WHERE s.enabled = true
    """)
    for row in rows:
        signal = await fetch_signal(pg_conn, row["id"])
        if signal:
            await publish_meta(mqtt_client, signal)
    log.info("initial reconciliation complete", count=len(rows))
```

### 5. Main (`app/main.py`)

```python
import asyncio
import asyncpg
import aiomqtt
import structlog
from app.config import settings
from app.notify_listener import listen_for_changes
from app.reconciler import (
    fetch_signal, publish_meta, delete_meta,
    reconcile_all, build_meta_topic
)

log = structlog.get_logger()

async def run():
    # Conexión Postgres para queries
    pg_pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        user=settings.postgres_user,
        password=settings.postgres_password,
        database=settings.postgres_db,
    )

    async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as mqtt_client:
        # 1. Reconciliación inicial: publicar $meta de todas las señales
        async with pg_pool.acquire() as conn:
            await reconcile_all(conn, mqtt_client)

        # 2. Callback para cambios
        async def on_change(payload: dict):
            op = payload["op"]
            signal_id = payload["id"]
            async with pg_pool.acquire() as conn:
                if op == "DELETE":
                    # No podemos consultar la fila (ya no existe).
                    # Necesitamos haber guardado el topic antes... o suscribirnos al BEFORE DELETE.
                    # Para simplificar: el trigger envía también el topic en el payload.
                    log.warning("DELETE handling requires topic in payload", id=signal_id)
                    return
                signal = await fetch_signal(conn, signal_id)
                if signal:
                    await publish_meta(mqtt_client, signal)

        # 3. Escuchar indefinidamente
        await listen_for_changes(on_change)

if __name__ == "__main__":
    asyncio.run(run())
```

### 6. Mejora del trigger para incluir el topic en DELETE

El payload del trigger actual solo lleva `op` e `id`. Para gestionar DELETE bien, modifica el trigger:

```sql
CREATE OR REPLACE FUNCTION notify_signal_change()
RETURNS TRIGGER AS $$
DECLARE
    payload JSON;
BEGIN
    IF TG_OP = 'DELETE' THEN
        payload := json_build_object(
            'op', TG_OP,
            'id', OLD.id,
            'topic', OLD.topic,
            'name', OLD.name,
            'asset_id', OLD.asset_id
        );
    ELSE
        payload := json_build_object(
            'op', TG_OP,
            'id', NEW.id
        );
    END IF;
    PERFORM pg_notify('signals_changed', payload::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
```

Y el callback maneja DELETE:

```python
async def on_change(payload: dict):
    op = payload["op"]
    if op == "DELETE":
        # Construir el topic $meta a partir del topic original
        # OLD.topic era ".../measure/<name>"; el $meta está en ".../$meta/<name>"
        original_topic = payload["topic"]
        parts = original_topic.split("/")
        # Reemplazar el penúltimo segmento ('measure'/'events') por '$meta'
        parts[-2] = "$meta"
        meta_topic = "/".join(parts)
        await delete_meta(mqtt_client, meta_topic)
        return
    # INSERT/UPDATE: igual que antes
    signal_id = payload["id"]
    async with pg_pool.acquire() as conn:
        signal = await fetch_signal(conn, signal_id)
        if signal:
            await publish_meta(mqtt_client, signal)
```

### 7. docker-compose

```yaml
  sync-service:
    build: ./services/sync-service
    container_name: sync-service
    depends_on:
      - postgres
      - mqtt-broker
    environment:
      MQTT_HOST: mqtt-broker
      POSTGRES_HOST: postgres
      POSTGRES_USER: aeronorth
      POSTGRES_PASSWORD: changeme
      POSTGRES_DB: aeronorth
```

### 8. Arranca y prueba

```bash
docker compose up -d --build sync-service
docker compose logs -f sync-service
```

En otra terminal, suscríbete a `$meta`:

```bash
mosquitto_sub -h localhost -p 1883 -t '+/+/+/+/+/$meta/#' -v
```

Ve al `http://localhost:8000/admin`, da de alta una señal nueva (asegúrate de que el asset existe). En la terminal de `mosquitto_sub` deberías ver llegar el `$meta` correspondiente al instante.

Más prueba: cierra `mosquitto_sub`, vuelve a abrirlo. El broker te entrega los `$meta` retenidos inmediatamente — aunque la publicación fue hace tiempo.

## Lo que has aprendido

- Cómo usar LISTEN/NOTIFY de Postgres con asyncpg.
- Cómo el patrón "fuente de verdad + espejo" mantiene consistente el sistema.
- Cómo publicar mensajes retenidos y cómo borrarlos.
- Cómo hacer reconciliación al arranque para garantizar consistencia incluso si el broker se reinició.

## Lo que NO has hecho todavía

- Visualizar nada en navegador (módulo 6).
- Aplicar criticidad (módulo 7).
- Eventos (módulo 8).

## Comprobación final

- [ ] `sync-service` corre sin errores.
- [ ] Al crear una señal en SQLAdmin, aparece el `$meta` en el broker.
- [ ] Al borrar una señal, el `$meta` desaparece del broker.
- [ ] Si reinicias el broker, al arrancar `sync-service` republica todos los `$meta`.

## Siguiente módulo

[Módulo 6 — Frontend mínimo y realtime-service](15-modulo-06-frontend-realtime.md)
