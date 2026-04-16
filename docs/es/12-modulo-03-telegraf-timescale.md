# Módulo 3 — Persistencia con Telegraf y TimescaleDB

## Objetivo

Persistir la telemetría que publica el simulador en una base de datos time-series (TimescaleDB) usando Telegraf como agente de ingesta. Al terminar, podrás consultar el histórico con SQL y ver cómo evolucionan las señales en el tiempo.

**Tiempo estimado**: 1-2 horas.

## Conceptos que vas a manejar

- **TimescaleDB**: extensión de PostgreSQL optimizada para series temporales.
- **Hypertable**: tabla particionada automáticamente por tiempo.
- **Telegraf**: agente de ingesta sin código, configurado con un fichero TOML.
- **Topic parsing**: extraer información del topic MQTT y convertirla en columnas/tags de la base de datos.

## Lo que vas a montar

Añadir al `docker-compose.yml`:
- `timescaledb`: base de datos time-series.
- `telegraf`: agente que se suscribe al broker y escribe en TimescaleDB.

## Por qué Telegraf

Podríamos escribir un microservicio Python que se suscribe a MQTT y escribe en Postgres. Funcionaría. Pero para el caso "lee mensajes simples y escríbelos a una BBDD", Telegraf es más eficiente y no requiere mantener código. Lo configuramos con un fichero TOML y listo.

La contrapartida es que Telegraf es **rígido**: no puede hacer lógica compleja como "consulta el registro Postgres antes de insertar". Para casos así (eventos enriquecidos, validaciones), tendremos microservicios Python propios. Pero para telemetría informativa pura, Telegraf brilla.

## Paso a paso

### 1. Añade TimescaleDB al docker-compose

```yaml
services:
  # ... (mqtt-broker, simulator)

  timescaledb:
    image: timescale/timescaledb:latest-pg16
    container_name: timescaledb
    ports:
      - "5433:5432"
    environment:
      POSTGRES_DB: metrics
      POSTGRES_USER: telegraf
      POSTGRES_PASSWORD: changeme
    volumes:
      - timescale-data:/var/lib/postgresql/data
      - ./infra/timescale-init:/docker-entrypoint-initdb.d:ro

volumes:
  emqx-data:
  emqx-log:
  timescale-data:
```

Nota: usamos el puerto **5433** en el host (no 5432) para no chocar con el Postgres del registro que añadiremos en el módulo 4.

### 2. Script de inicialización de TimescaleDB

Crea `infra/timescale-init/01-init.sql`:

```sql
-- Habilitar la extensión TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Tabla para métricas
CREATE TABLE IF NOT EXISTS metrics (
    time      TIMESTAMPTZ NOT NULL,
    topic     TEXT NOT NULL,
    value     DOUBLE PRECISION,
    quality   SMALLINT DEFAULT 1
);

-- Convertir a hypertable (particionada por tiempo)
SELECT create_hypertable('metrics', 'time', if_not_exists => TRUE);

-- Índice para consultas por topic + tiempo (las más comunes)
CREATE INDEX IF NOT EXISTS idx_metrics_topic_time
    ON metrics (topic, time DESC);

-- Política de retención: borrar datos > 1 año
SELECT add_retention_policy('metrics', INTERVAL '1 year', if_not_exists => TRUE);
```

Este script se ejecuta automáticamente la primera vez que arranca el contenedor.

### 3. Configuración de Telegraf

Crea `infra/telegraf/telegraf.conf`:

```toml
[agent]
  interval = "10s"
  flush_interval = "10s"
  omit_hostname = true

# ===== Input: MQTT =====
[[inputs.mqtt_consumer]]
  servers = ["tcp://mqtt-broker:1883"]
  topics = ["+/+/+/+/+/measure/#"]
  qos = 0
  client_id = "telegraf-ingestor"
  data_format = "json"
  json_string_fields = []
  json_time_key = "ts"
  json_time_format = "unix_ms"

  # Renombrar el campo "val" a "value"
  [[inputs.mqtt_consumer.json_v2]]
    measurement_name = "metrics"
    [[inputs.mqtt_consumer.json_v2.field]]
      path = "val"
      rename = "value"
      type = "float"
    [[inputs.mqtt_consumer.json_v2.field]]
      path = "q"
      rename = "quality"
      type = "int"

  # Parsear el topic en tags
  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "+/+/+/+/+/measure/+"
    tags = "enterprise/site/area/line/cell/_/signal_name"

# ===== Output: PostgreSQL (TimescaleDB) =====
[[outputs.postgresql]]
  connection = "host=timescaledb port=5432 user=telegraf password=changeme dbname=metrics sslmode=disable"
  schema = "public"
  table_template = '''
    CREATE TABLE {TABLE} (
      time TIMESTAMPTZ NOT NULL,
      topic TEXT NOT NULL,
      value DOUBLE PRECISION,
      quality SMALLINT
    )
  '''
  tags_as_jsonb = false
  tags_as_foreign_keys = false

# Plugin custom para componer el "topic" completo a partir de los tags
# (en producción esto se haría con un processor)

# ===== Logging =====
[[outputs.file]]
  files = ["stdout"]
  data_format = "influx"
```

**Importante**: Telegraf necesita una pequeña adaptación para componer el topic completo. La forma más limpia es usar un processor `starlark` o, más sencillo para el curso, hacer la transformación a la entrada en un script Python ligero que escuche y reescriba al output. Para mantenerlo simple, en este módulo dejamos el topic como tag separado y compondremos al consultar.

**Versión simplificada del telegraf.conf** (la que usaremos):

```toml
[agent]
  interval = "10s"
  flush_interval = "10s"
  omit_hostname = true

[[inputs.mqtt_consumer]]
  servers = ["tcp://mqtt-broker:1883"]
  topics = ["+/+/+/+/+/measure/#"]
  qos = 0
  client_id = "telegraf-ingestor"
  data_format = "json"
  json_time_key = "ts"
  json_time_format = "unix_ms"

  [[inputs.mqtt_consumer.topic_parsing]]
    topic = "+/+/+/+/+/measure/+"
    measurement = "_/_/_/_/_/_/_"
    tags = "enterprise/site/area/line/cell/_/signal"

[[outputs.postgresql]]
  connection = "host=timescaledb port=5432 user=telegraf password=changeme dbname=metrics sslmode=disable"
```

### 4. Añade Telegraf al docker-compose

```yaml
  telegraf:
    image: telegraf:1.32
    container_name: telegraf
    depends_on:
      - mqtt-broker
      - timescaledb
    volumes:
      - ./infra/telegraf/telegraf.conf:/etc/telegraf/telegraf.conf:ro
```

### 5. Arranca todo

```bash
docker compose up -d --build
docker compose logs -f telegraf
```

Si Telegraf arranca bien, verás algo como:

```
2024-01-16T10:00:00Z I! Loaded inputs: mqtt_consumer
2024-01-16T10:00:00Z I! Loaded outputs: postgresql
2024-01-16T10:00:00Z I! Tags enabled: ...
```

Si hay errores, normalmente son:
- Telegraf arranca antes que TimescaleDB esté lista → reinicia Telegraf
- Credenciales mal → revisa el `.conf`

### 6. Comprueba que se están escribiendo datos

Conecta a TimescaleDB:

```bash
docker compose exec timescaledb psql -U telegraf -d metrics
```

Lista las tablas:

```sql
\dt
```

Deberías ver tablas autogeneradas por Telegraf con los nombres de las señales. Para una vista unificada, consulta una tabla específica:

```sql
SELECT * FROM mqtt_consumer LIMIT 10;
```

O cuenta filas:

```sql
SELECT COUNT(*) FROM mqtt_consumer;
```

Si ves filas que aumentan cada 10 segundos, ¡funciona!

### 7. Tu primera consulta time-series

```sql
-- Últimas 10 muestras de wind_speed
SELECT time, value
FROM mqtt_consumer
WHERE signal = 'wind_speed'
ORDER BY time DESC
LIMIT 10;

-- Promedio de potencia activa por minuto en la última hora
SELECT
  time_bucket('1 minute', time) AS bucket,
  AVG(value) AS avg_power
FROM mqtt_consumer
WHERE signal = 'active_power'
  AND time > NOW() - INTERVAL '1 hour'
GROUP BY bucket
ORDER BY bucket DESC;
```

`time_bucket()` es una función nativa de TimescaleDB para agrupar por intervalos de tiempo. Mucho más rápido que el `date_trunc` de Postgres puro.

## Limitaciones del setup actual

Este módulo deja Telegraf con una configuración funcional pero básica. Limitaciones que iremos resolviendo:

- **El "topic" completo no se reconstruye fácilmente** porque Telegraf parsea cada nivel a un tag separado. Para nuestra documentación oficial usamos una columna `topic` única; aquí tenemos `enterprise + site + ... + signal` por separado. En el módulo 4, cuando creemos el `api-service`, las consultas reconstruirán el topic concatenando.
- **No estamos escribiendo en Redis todavía** (LKV). Eso entra en el módulo 7.
- **No estamos diferenciando por criticidad**. Todo se escribe igual. También módulo 7.

## Lo que has aprendido

- A levantar TimescaleDB con la extensión activada.
- A convertir una tabla normal en hypertable.
- A configurar Telegraf con `mqtt_consumer` + `postgresql`.
- A parsear topics MQTT en tags estructurados.
- A consultar series temporales con `time_bucket()` y agregaciones.

## Comprobación final

- [ ] El contenedor `timescaledb` está corriendo.
- [ ] El contenedor `telegraf` está corriendo sin errores en logs.
- [ ] Hay filas en la BBDD que crecen cada 10 segundos.
- [ ] Puedes hacer un `SELECT` y ver datos del simulador.

## Siguiente módulo

[Módulo 4 — El registro UNS y el api-service](13-modulo-04-api-service.md)
