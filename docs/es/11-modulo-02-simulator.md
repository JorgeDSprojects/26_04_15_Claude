# Módulo 2 — El simulador y la jerarquía ISA-95

## Objetivo

Construir el primer servicio propio: un simulador en Python que publica datos de una turbina eólica al broker, siguiendo topics ISA-95. Al terminar, verás telemetría en tiempo real (viento, RPM, potencia) llegar al broker cada pocos segundos.

**Tiempo estimado**: 1-2 horas.

## Conceptos que vas a manejar

- **Servicio dockerizado**: una pieza de software corriendo en su propio contenedor, comunicándose con otros servicios solo por red.
- **Cliente MQTT en Python**: la librería `aiomqtt` (asyncio-friendly).
- **asyncio**: programación asíncrona en Python.
- **Topic ISA-95 completo**: `enterprise/site/area/line/cell/namespace/signal_name`.
- **Payload optimizado**: `{"val": ..., "ts": ..., "q": ...}`.

## Lo que vas a montar

Añadir al `docker-compose.yml`:
- `simulator`: contenedor Python que publica datos de **una turbina** (turbine_03) al broker.

## Paso a paso

### 1. Estructura del servicio

```
services/simulator/
├── app/
│   ├── __init__.py
│   ├── main.py
│   └── config.py
├── data/
│   └── wind_turbine_data.csv
├── Dockerfile
├── pyproject.toml
└── README.md
```

### 2. Dataset

Descarga el dataset Kaggle "Wind Turbine SCADA Dataset" o usa el fichero `T1.csv` que se distribuye habitualmente. Las columnas que nos interesan:

- `Date/Time` → timestamp (se ignora, usamos el actual)
- `LV ActivePower (kW)` → `active_power`
- `Wind Speed (m/s)` → `wind_speed`
- `Wind Direction (°)` → `wind_direction`
- `Theoretical_Power_Curve (KWh)` → no se publica, solo referencia

Coloca el CSV en `services/simulator/data/wind_turbine_data.csv`.

### 3. Dependencias (`pyproject.toml`)

```toml
[project]
name = "simulator"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "aiomqtt>=2.3",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
]
```

### 4. Configuración (`app/config.py`)

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mqtt_host: str = "mqtt-broker"
    mqtt_port: int = 1883
    sim_csv_path: str = "/data/wind_turbine_data.csv"
    sim_interval_s: int = 10
    sim_turbine_code: str = "turbine_03"
    sim_asset_path: str = (
        "aeronorth/windfarm_north/sector_a/turbine_03"
    )

settings = Settings()
```

### 5. El bucle principal (`app/main.py`) — versión mínima

```python
import asyncio
import csv
import json
import time
import structlog
import aiomqtt
from app.config import settings

log = structlog.get_logger()

# Mapeo: columna del CSV → (componente, nombre de señal)
CSV_TO_SIGNAL = {
    "LV ActivePower (kW)": ("generator", "active_power"),
    "Wind Speed (m/s)":    ("nacelle", "wind_speed"),
    "Wind Direction (°)":  ("nacelle", "wind_direction"),
}

def build_topic(component: str, signal: str) -> str:
    return f"{settings.sim_asset_path}/{component}/measure/{signal}"

def build_payload(value: float) -> bytes:
    return json.dumps({
        "val": float(value),
        "ts": int(time.time() * 1000),
        "q": 1,
    }).encode()

async def read_csv_loop():
    while True:
        with open(settings.sim_csv_path) as f:
            reader = csv.DictReader(f)
            async with aiomqtt.Client(settings.mqtt_host, settings.mqtt_port) as client:
                for row in reader:
                    for csv_col, (comp, sig) in CSV_TO_SIGNAL.items():
                        if csv_col not in row or not row[csv_col]:
                            continue
                        try:
                            value = float(row[csv_col])
                        except ValueError:
                            continue
                        topic = build_topic(comp, sig)
                        payload = build_payload(value)
                        await client.publish(topic, payload, qos=0)
                        log.info("published", topic=topic, val=value)
                    await asyncio.sleep(settings.sim_interval_s)

async def main():
    log.info("simulator starting", config=settings.model_dump())
    while True:
        try:
            await read_csv_loop()
        except Exception as e:
            log.error("loop crashed, retrying", error=str(e))
            await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(main())
```

### 6. Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app/ ./app/
CMD ["python", "-m", "app.main"]
```

### 7. Añade el servicio al `docker-compose.yml`

```yaml
services:
  mqtt-broker:
    # (igual que en módulo 1)

  simulator:
    build: ./services/simulator
    container_name: simulator
    depends_on:
      - mqtt-broker
    environment:
      MQTT_HOST: mqtt-broker
      MQTT_PORT: 1883
      SIM_CSV_PATH: /data/wind_turbine_data.csv
      SIM_INTERVAL_S: 10
    volumes:
      - ./services/simulator/data:/data:ro
```

### 8. Arranca y observa

```bash
docker compose up -d --build
docker compose logs -f simulator
```

En **otra terminal**, suscríbete y mira los datos llegar:

```bash
mosquitto_sub -h localhost -p 1883 -t '+/+/+/+/+/measure/#' -v
```

Deberías ver salir mensajes cada 10 segundos:

```
aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power {"val": 850.3, "ts": 1705400100500, "q": 1}
aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed {"val": 12.3, "ts": 1705400100500, "q": 1}
aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_direction {"val": 245.7, "ts": 1705400100500, "q": 1}
```

### 9. Comprueba en el dashboard EMQX

Vuelve a `http://localhost:18083`. En "Topics" verás aparecer los tres topics. En "Metrics" verás la tasa de mensajes/segundo aumentar.

## Ejercicios opcionales

1. **Añade más señales**: amplía `CSV_TO_SIGNAL` con campos sintéticos. Por ejemplo, RPM del rotor calculado como `wind_speed * 1.2` (aproximación simplificada).

2. **Implementa Report by Exception**: solo publica si el valor cambió respecto al anterior. Mantén un dict en memoria con el último valor por señal.

3. **Aleatorización**: añade ruido gaussiano (`random.gauss(value, value*0.02)`) para que los valores no sean idénticos a los del CSV cada ciclo.

4. **Múltiples turbinas**: refactoriza para publicar las 6 turbinas en paralelo. Usa `asyncio.gather()`.

## Lo que has aprendido

- A construir un servicio Python en Docker que se conecta a MQTT.
- A usar `aiomqtt` para publicación async.
- A estructurar topics siguiendo ISA-95.
- A usar el formato de payload optimizado `{"val", "ts", "q"}`.
- A leer un CSV y republicarlo como streaming.

## Lo que NO has hecho todavía

- Persistir nada (módulo 3).
- Mantener un registro de qué señales existen (módulo 4).
- Publicar `$meta` o eventos (módulos 5 y 8).

## Comprobación final

- [ ] El contenedor `simulator` está corriendo y publicando.
- [ ] Ves los mensajes llegar con `mosquitto_sub`.
- [ ] Los topics siguen la jerarquía ISA-95.
- [ ] El payload tiene formato JSON con `val`, `ts`, `q`.

## Siguiente módulo

[Módulo 3 — Persistencia con Telegraf y TimescaleDB](12-modulo-03-telegraf-timescale.md)
