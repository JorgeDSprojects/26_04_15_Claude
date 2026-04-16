# Módulo 7 — Criticidad, Redis y buffers

## Objetivo

Implementar el modelo de criticidad de tres niveles. Añadir Redis al sistema para dos cosas: el "último valor conocido" (LKV) que permite que un widget recién abierto muestre datos al instante, y los "Streams" que permiten al cliente reconectar y recuperar lo que se perdió.

Al terminar, podrás recargar el navegador y ver el gráfico aparecer instantáneamente con el último valor; podrás cerrar la pestaña 30 segundos, abrirla de nuevo y ver cómo el hueco se rellena para señales `buffered`/`critical`.

**Tiempo estimado**: 3-4 horas.

## Conceptos que vas a manejar

- **Redis** como almacén key-value en memoria.
- **Redis Streams**: estructura de log/cola con lectura desde un punto.
- **Catch-up**: reenviar mensajes perdidos durante una desconexión.
- **Criticidad** aplicada en código: branching por nivel.

## Lo que vas a montar

- `redis`: servicio Redis 7.x.
- Modificar `telegraf.conf` para que escriba también en Redis (LKV).
- Modificar `realtime-service` para usar criticidad y Redis Streams.

## Las dos funciones de Redis

Recordemos lo del módulo 04-modelo-criticidad:

1. **LKV (Last Known Value)**: clave `lkv:<topic>` con el último valor publicado. Lo escribe Telegraf en cada mensaje. Lo lee `realtime-service` cuando un cliente se suscribe a un topic.

2. **Streams para continuidad**: clave `stream:<topic>` con un Redis Stream que mantiene los últimos N mensajes. Lo escribe `realtime-service` solo para señales `buffered` o `critical`. Lo lee `realtime-service` al reconectar un cliente.

## Paso a paso

### 1. Añade Redis al docker-compose

```yaml
  redis:
    image: redis:7-alpine
    container_name: redis
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

volumes:
  # ...
  redis-data:
```

Comprueba:

```bash
docker compose up -d redis
docker compose exec redis redis-cli PING
# debería responder PONG
```

### 2. Modifica Telegraf para escribir LKV

Telegraf no tiene un output nativo de Redis hash/set "elegante", pero sí tiene un output a Redis genérico (`outputs.redis_timeseries` o usar un script intermedio).

**Aproximación pragmática para el curso**: añadir un pequeño servicio Python que se suscribe al broker y escribe LKV en Redis. Es más sencillo de entender que pelear con la configuración avanzada de Telegraf.

Crea `services/lkv-writer/`:

```
services/lkv-writer/
├── app/
│   ├── __init__.py
│   └── main.py
├── Dockerfile
└── pyproject.toml
```

`app/main.py`:

```python
import asyncio
import json
import structlog
import aiomqtt
import redis.asyncio as aioredis
from app.config import settings  # análogo a otros servicios

log = structlog.get_logger()

async def run():
    r = aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                await client.subscribe("+/+/+/+/+/measure/#")
                async for msg in client.messages:
                    topic = str(msg.topic)
                    payload = msg.payload.decode()
                    await r.set(f"lkv:{topic}", payload)
        except Exception as e:
            log.error("lkv loop crashed", error=str(e))
            await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(run())
```

Añádelo al docker-compose:

```yaml
  lkv-writer:
    build: ./services/lkv-writer
    container_name: lkv-writer
    depends_on:
      - mqtt-broker
      - redis
    environment:
      MQTT_HOST: mqtt-broker
      REDIS_HOST: redis
```

**Nota**: en producción, optimizarías esto para no tener un proceso Python solo por una instrucción `SET`. Para el curso es lo más claro.

### 3. Comprueba LKV

```bash
docker compose up -d --build lkv-writer
sleep 30  # deja que llegue algún dato
docker compose exec redis redis-cli
> KEYS lkv:*
> GET lkv:aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed
```

### 4. Modifica realtime-service: cargar criticidad del registro

El `realtime-service` necesita saber la criticidad de cada topic. Lo más limpio: al arrancar, hace una llamada HTTP a `api-service` y se trae el mapeo `topic → criticidad`. Cuando llega un `$meta` actualizado, refresca el cache.

Añade a `realtime-service/app/signal_cache.py`:

```python
import asyncio
import httpx
import json
import structlog
import aiomqtt
from app.config import settings

log = structlog.get_logger()

class SignalCache:
    def __init__(self):
        self.criticality_by_topic: dict[str, str] = {}

    async def load_initial(self):
        url = f"{settings.api_service_url}/api/v1/signals?enabled=true"
        async with httpx.AsyncClient() as c:
            resp = await c.get(url)
            for s in resp.json():
                self.criticality_by_topic[s["topic"]] = s["criticality"]
        log.info("initial cache loaded", count=len(self.criticality_by_topic))

    async def listen_meta_updates(self):
        async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
            await client.subscribe("+/+/+/+/+/$meta/#")
            async for msg in client.messages:
                if not msg.payload:
                    # Retained borrado: la señal fue eliminada
                    self._remove_meta(str(msg.topic))
                    continue
                try:
                    meta = json.loads(msg.payload)
                    measure_topic = self._meta_to_measure_topic(str(msg.topic))
                    self.criticality_by_topic[measure_topic] = meta["criticality"]
                except Exception as e:
                    log.warning("bad $meta", error=str(e))

    def get(self, topic: str) -> str:
        return self.criticality_by_topic.get(topic, "standard")

    def _meta_to_measure_topic(self, meta_topic: str) -> str:
        parts = meta_topic.split("/")
        # Reemplazar '$meta' por 'measure'
        idx = parts.index("$meta")
        parts[idx] = "measure"
        return "/".join(parts)

    def _remove_meta(self, meta_topic: str):
        measure_topic = self._meta_to_measure_topic(meta_topic)
        self.criticality_by_topic.pop(measure_topic, None)

cache = SignalCache()
```

### 5. Modifica realtime-service: usar Redis Stream

Modifica `app/mqtt_listener.py`:

```python
import asyncio
import json
import structlog
import aiomqtt
import redis.asyncio as aioredis
from app.ws_manager import manager
from app.signal_cache import cache
from app.config import settings

log = structlog.get_logger()

STREAM_MAXLEN = {"standard": 0, "buffered": 1000, "critical": 10000}

async def mqtt_loop():
    r = aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                await client.subscribe("+/+/+/+/+/measure/#")
                await client.subscribe("+/+/+/+/+/events/#")
                async for msg in client.messages:
                    topic = str(msg.topic)
                    payload = msg.payload
                    crit = cache.get(topic)

                    if crit in ("buffered", "critical"):
                        await r.xadd(
                            f"stream:{topic}",
                            {"payload": payload},
                            maxlen=STREAM_MAXLEN[crit],
                            approximate=True,
                        )

                    try:
                        decoded = json.loads(payload)
                    except Exception:
                        decoded = {"raw": payload.decode(errors="replace")}
                    await manager.publish(topic, decoded)
        except Exception as e:
            log.error("mqtt loop", error=str(e))
            await asyncio.sleep(3)
```

### 6. Modifica WSManager: enviar LKV al suscribirse

En `app/ws_manager.py`:

```python
import redis.asyncio as aioredis
import json

class WSManager:
    def __init__(self, redis_client):
        self.subscribers = defaultdict(set)
        self.lock = asyncio.Lock()
        self.r = redis_client

    async def subscribe(self, ws, topics):
        async with self.lock:
            for topic in topics:
                self.subscribers[topic].add(ws)
        # Enviar LKV inmediato
        for topic in topics:
            lkv = await self.r.get(f"lkv:{topic}")
            if lkv:
                try:
                    payload = json.loads(lkv)
                except Exception:
                    payload = {"raw": lkv.decode()}
                await ws.send_text(json.dumps({
                    "topic": topic,
                    "payload": payload,
                    "lkv": True
                }))
```

### 7. Catch-up al reconectar (criticality buffered/critical)

Aquí es donde se pone interesante. El cliente lleva un `client_id` (ej. UUID generado por el navegador y guardado en sessionStorage) que persiste entre reconexiones. El `realtime-service` mantiene en Redis un hash `ws:session:<client_id>` con el último stream ID leído por topic.

Modifica el handler WebSocket para aceptar un `client_id` en el handshake:

```python
@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, client_id: str = Query(...)):
    await ws.accept()
    # En el subscribe, además de añadir a la lista, hacer catch-up:
    # 1. Para cada topic buffered/critical:
    #    last_id = HGET ws:session:<client_id> <topic>
    #    if last_id:
    #        msgs = XREAD stream:<topic> from last_id
    #        send each msg to ws
    #        update last_id
```

Para no extender este tutorial demasiado, te propongo el ejercicio de implementar el catch-up tú mismo. La estructura es:

1. Cliente abre WS con `?client_id=abc123`.
2. Cliente envía `{"action": "subscribe", "topics": [...]}`.
3. Servidor:
   - Para cada topic, mira la criticidad.
   - Si es standard: solo envía LKV.
   - Si es buffered/critical: lee el último ID conocido del cliente para ese topic; lee del stream desde ese ID con `XREAD`; envía mensajes; actualiza el último ID.
4. A partir de ahí, los mensajes nuevos llegan por el flujo normal MQTT → WS.

### 8. Frontend: añadir client_id

```javascript
function getClientId() {
  let id = sessionStorage.getItem("aeronorth_client_id");
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem("aeronorth_client_id", id);
  }
  return id;
}

// En useWebSocket:
const ws = new WebSocket(`${url}?client_id=${getClientId()}`);
```

### 9. Pruebas de aceptación

**Prueba LKV**: refresca la página; el gráfico debería mostrar inmediatamente el último valor sin esperar el próximo mensaje MQTT.

**Prueba catch-up buffered**: con la página abierta y datos llegando, abre las DevTools del navegador → Network → WebSocket → bloquea la conexión durante 30 segundos. Desbloquea. Si la señal es `buffered`, deberías ver llegar de golpe los mensajes que pasaron durante el bloqueo.

**Prueba que standard no hace catch-up**: lo mismo con una señal `standard`. Solo debería llegar el siguiente mensaje "fresco", no los que se perdieron.

## Lo que has aprendido

- Cómo Redis sirve de cache (LKV) para datos al instante.
- Cómo Redis Streams permiten un buffer corto con lectura desde un punto.
- Cómo aplicar la criticidad de cada señal en el flujo de mensajes.
- Cómo el `realtime-service` mantiene cache local de metadatos sincronizado con `$meta` retenidos.

## Comprobación final

- [ ] Redis corre.
- [ ] El LKV se actualiza con cada mensaje del simulador.
- [ ] Al recargar la página, los gráficos muestran el último valor sin esperar.
- [ ] Para señales `buffered`, una desconexión corta no deja huecos visibles.

## Siguiente módulo

[Módulo 8 — Eventos, alarmas y QoS 1](17-modulo-08-eventos-alarmas.md)
