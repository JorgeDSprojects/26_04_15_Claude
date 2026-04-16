# Módulo 6 — Frontend mínimo y realtime-service

## Objetivo

Cerrar el bucle hasta el navegador. Construir un servicio WebSocket que haga de puente entre MQTT y el navegador, y un frontend React mínimo con un único widget de gráfico. Al terminar, verás los datos del simulador llegar a una gráfica en el navegador en tiempo real.

**Tiempo estimado**: 3-4 horas.

## Conceptos que vas a manejar

- **WebSocket** como protocolo bidireccional entre navegador y servidor.
- **Fan-out**: un mensaje recibido del broker se reenvía a múltiples clientes.
- **Suscripción dinámica**: cada cliente declara qué topics quiere.
- **React + Vite** como base de frontend moderno.
- **Plotly.js** para gráficos interactivos.

## Lo que vas a montar

- `realtime-service`: FastAPI con WebSockets que hace de puente MQTT → navegador.
- `frontend`: React + Vite con un widget de gráfica simple.

## La regla de oro: el navegador NO habla MQTT

Podríamos usar MQTT-over-WebSocket directo entre EMQX y el navegador. EMQX lo soporta. Pero entonces:
- Tendríamos que gestionar la auth del broker desde el navegador (complicado, expone credenciales).
- Cada navegador sería un cliente MQTT más en el broker (no escala bien con muchos usuarios).
- Perderíamos la oportunidad de filtrar/transformar/throttling antes de mandar al navegador.

Por eso ponemos un servicio intermedio. El navegador habla un protocolo simple (WebSocket con mensajes JSON) y el servicio se encarga de la parte MQTT.

## Paso a paso

### 1. realtime-service: estructura

```
services/realtime-service/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── mqtt_listener.py    # Suscripción a MQTT
│   ├── ws_manager.py       # Gestión de clientes WS
│   └── router.py           # Endpoint WS
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 2. Dependencias

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "aiomqtt>=2.3",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
]
```

### 3. WebSocket manager (`app/ws_manager.py`)

```python
import asyncio
import json
import structlog
from collections import defaultdict
from fastapi import WebSocket

log = structlog.get_logger()

class WSManager:
    def __init__(self):
        # topic -> set of WebSocket
        self.subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        self.lock = asyncio.Lock()

    async def subscribe(self, ws: WebSocket, topics: list[str]):
        async with self.lock:
            for topic in topics:
                self.subscribers[topic].add(ws)
        log.info("client subscribed", topics=topics)

    async def unsubscribe(self, ws: WebSocket, topics: list[str] | None = None):
        async with self.lock:
            if topics is None:
                # Eliminar de todas las suscripciones
                for s in self.subscribers.values():
                    s.discard(ws)
            else:
                for topic in topics:
                    self.subscribers[topic].discard(ws)

    async def publish(self, topic: str, payload: dict):
        """Cuando llega un mensaje MQTT, hace fan-out a los suscriptores."""
        async with self.lock:
            clients = list(self.subscribers.get(topic, []))
        msg = json.dumps({"topic": topic, "payload": payload})
        for client in clients:
            try:
                await client.send_text(msg)
            except Exception as e:
                log.warning("send failed", error=str(e))

manager = WSManager()
```

### 4. MQTT listener (`app/mqtt_listener.py`)

```python
import asyncio
import json
import structlog
import aiomqtt
from app.ws_manager import manager
from app.config import settings

log = structlog.get_logger()

async def mqtt_loop():
    while True:
        try:
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                # Suscríbete a todo (en módulos posteriores afinaremos por criticidad)
                await client.subscribe("+/+/+/+/+/measure/#")
                await client.subscribe("+/+/+/+/+/events/#")
                async for msg in client.messages:
                    try:
                        payload = json.loads(msg.payload.decode())
                    except Exception:
                        payload = {"raw": msg.payload.decode(errors="replace")}
                    await manager.publish(str(msg.topic), payload)
        except Exception as e:
            log.error("mqtt loop error, reconnecting", error=str(e))
            await asyncio.sleep(3)
```

### 5. WebSocket router (`app/router.py`)

```python
import json
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.ws_manager import manager

log = structlog.get_logger()
router = APIRouter()

@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("client connected")
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_text(json.dumps({"error": "invalid json"}))
                continue

            action = msg.get("action")
            topics = msg.get("topics", [])

            if action == "subscribe":
                await manager.subscribe(ws, topics)
                await ws.send_text(json.dumps({"ok": "subscribed", "topics": topics}))
            elif action == "unsubscribe":
                await manager.unsubscribe(ws, topics)
                await ws.send_text(json.dumps({"ok": "unsubscribed"}))
            else:
                await ws.send_text(json.dumps({"error": "unknown action"}))
    except WebSocketDisconnect:
        await manager.unsubscribe(ws)
        log.info("client disconnected")
```

### 6. Main (`app/main.py`)

```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.router import router
from app.mqtt_listener import mqtt_loop
from app.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(mqtt_loop())
    yield
    task.cancel()

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
```

### 7. docker-compose

```yaml
  realtime-service:
    build: ./services/realtime-service
    container_name: realtime-service
    ports:
      - "8001:8001"
    depends_on:
      - mqtt-broker
    environment:
      MQTT_HOST: mqtt-broker
    command: uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### 8. Frontend React: estructura

```
services/frontend/
├── src/
│   ├── main.jsx
│   ├── App.jsx
│   ├── api/
│   │   └── client.js
│   ├── hooks/
│   │   └── useWebSocket.js
│   └── components/
│       └── LiveChart.jsx
├── index.html
├── vite.config.js
├── package.json
└── README.md
```

### 9. Vite + React

```bash
cd services/frontend
npm create vite@latest . -- --template react
npm install plotly.js react-plotly.js
```

### 10. Hook de WebSocket (`src/hooks/useWebSocket.js`)

```javascript
import { useEffect, useRef, useState } from "react";

export function useWebSocket(url, topics) {
  const [data, setData] = useState({});
  const wsRef = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ action: "subscribe", topics }));
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.topic && msg.payload) {
        setData(prev => ({
          ...prev,
          [msg.topic]: [...(prev[msg.topic] || []), msg.payload].slice(-100)
        }));
      }
    };

    ws.onerror = (err) => console.error("WS error", err);

    return () => ws.close();
  }, [url, JSON.stringify(topics)]);

  return data;
}
```

### 11. Componente LiveChart (`src/components/LiveChart.jsx`)

```javascript
import Plot from "react-plotly.js";

export function LiveChart({ topic, dataPoints, title }) {
  const x = dataPoints.map(p => new Date(p.ts));
  const y = dataPoints.map(p => p.val);

  return (
    <Plot
      data={[{
        x, y,
        type: "scatter",
        mode: "lines+markers",
        name: title,
      }]}
      layout={{
        title,
        height: 400,
        xaxis: { title: "time" },
        yaxis: { title: "value" },
      }}
    />
  );
}
```

### 12. App (`src/App.jsx`)

```javascript
import { useWebSocket } from "./hooks/useWebSocket";
import { LiveChart } from "./components/LiveChart";

const TOPIC = "aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed";

function App() {
  const data = useWebSocket("ws://localhost:8001/ws", [TOPIC]);
  const points = data[TOPIC] || [];

  return (
    <div style={{ padding: 20 }}>
      <h1>AeroNorth — Live</h1>
      <LiveChart topic={TOPIC} dataPoints={points} title="Wind Speed (m/s)" />
      <p>Points: {points.length}</p>
    </div>
  );
}

export default App;
```

### 13. Frontend en docker-compose (modo desarrollo)

```yaml
  frontend:
    image: node:20-slim
    container_name: frontend
    working_dir: /app
    volumes:
      - ./services/frontend:/app
    ports:
      - "5173:5173"
    command: sh -c "npm install && npm run dev -- --host 0.0.0.0"
```

### 14. Arranca y prueba

```bash
docker compose up -d --build realtime-service frontend
```

Abre `http://localhost:5173`. Deberías ver una gráfica que se va llenando con los datos de viento del simulador, en tiempo real.

## Limitaciones del setup actual

- **No hay LKV ni catch-up**: si recargas la página, empiezas con la gráfica vacía hasta que llegue el siguiente mensaje. Eso lo arreglamos en el módulo 7 con Redis.
- **No hay distinción por criticidad**: todo se trata igual. Módulo 7.
- **El widget está hardcodeado**: solo muestra una señal específica. Lo dinamizamos en el módulo 9 con GridStack.
- **Sin autenticación**: cualquiera puede conectarse al WebSocket. Lo añadimos cuando integremos fastapi-users del módulo 4.

## Lo que has aprendido

- Cómo construir un servicio WebSocket con FastAPI.
- Cómo hacer fan-out de MQTT a múltiples clientes WS.
- Cómo conectar React a un WebSocket con un hook personalizado.
- Cómo usar Plotly.js para gráficos en tiempo real.

## Comprobación final

- [ ] `realtime-service` corre y acepta conexiones WS.
- [ ] El frontend carga en `http://localhost:5173`.
- [ ] La gráfica se va rellenando con datos en tiempo real.
- [ ] Si paras el simulador, la gráfica deja de actualizarse pero no rompe.

## Siguiente módulo

[Módulo 7 — Criticidad, Redis y buffers](16-modulo-07-criticidad-redis.md)
