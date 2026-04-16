Este documento recoge el plan de desarrollo enfocado para dar clase sobre este desarrollo


## Módulo 1 — El broker y los primeros mensajes

**Objetivo didáctico**: el alumno ve mensajes MQTT moviéndose y entiende qué es un broker pub/sub.

**Qué se monta**:
- `docker-compose.yml` con un único servicio: EMQX.
- El alumno usa `mosquitto_pub` / `mosquitto_sub` desde la línea de comandos para publicar y suscribirse.
- Se introduce el concepto de topic, wildcard (`+` y `#`), QoS y retained.

**Lo que el alumno se lleva**: "el broker es un cartero, los topics son direcciones, esto funciona".

**Lo que NO entra todavía**: nada de Postgres, nada de FastAPI, nada de criticidad. Solo broker.

## Módulo 2 — El simulador y la jerarquía ISA-95

**Objetivo didáctico**: introducir el concepto de UNS y de topic estructurado.

**Qué se monta**:
- Servicio `simulator` (Python, dockerizado) que publica datos sintéticos de **una sola turbina** con topics ISA-95.
- El alumno se suscribe con `mosquitto_sub` y ve los datos llegar.
- Se discuten las 4 capas (descriptive, informative, operational, analytic) de SOFIA.

**Lo que el alumno se lleva**: "ah, los topics no son arbitrarios, tienen una semántica jerárquica".

**Hito visible**: ver telemetría de viento, RPM y potencia llegar en vivo en la terminal.

## Módulo 3 — Persistencia con Telegraf y TimescaleDB

**Objetivo didáctico**: separar el "tiempo real" del "histórico" y entender por qué la BBDD time-series existe.

**Qué se monta**:
- TimescaleDB en docker-compose.
- Telegraf en docker-compose con `mqtt_consumer` y output a Postgres.
- El alumno hace queries SQL y ve datos históricos.

**Lo que el alumno se lleva**: "el broker no guarda nada, hace falta un consumidor que persista".

**Hito visible**: gráfica básica con `psql` o DBeaver mostrando la evolución del viento.

## Módulo 4 — El registro UNS y el api-service

**Objetivo didáctico**: introducir Postgres como "fuente de verdad" y FastAPI como puerta de entrada.

**Qué se monta**:
- Postgres (registro) en docker-compose, separado de TimescaleDB.
- `api-service` con FastAPI, SQLAlchemy async, las tablas del bloque 3.
- Endpoints CRUD básicos para `assets` y `signals`.
- SQLAdmin en `/admin`.
- Alembic con la primera migración.

**Lo que el alumno se lleva**: "ahora tengo dónde declarar oficialmente qué señales existen".

**Hito visible**: dar de alta una señal desde SQLAdmin y verla en la BBDD.

## Módulo 5 — El sync-service y LISTEN/NOTIFY

**Objetivo didáctico**: cerrar el círculo entre registro y broker.

**Qué se monta**:
- `sync-service` en docker-compose.
- Trigger LISTEN/NOTIFY en Postgres.
- El servicio publica `$meta` retained al broker cuando hay cambios.

**Lo que el alumno se lleva**: "Postgres es el maestro, MQTT es el espejo, los dos están sincronizados automáticamente".

**Hito visible**: dar de alta una señal en SQLAdmin → ver inmediatamente con `mosquitto_sub` el `$meta` retained aparecer en el broker.

## Módulo 6 — El frontend mínimo y el realtime-service

**Objetivo didáctico**: cerrar el bucle hasta el navegador.

**Qué se monta**:
- `realtime-service` con WebSockets (todavía sin criticidad, todo standard).
- Frontend React mínimo con un solo widget de gráfica usando Plotly.
- Conexión: navegador → REST al api-service para config, WS al realtime-service para datos.

**Lo que el alumno se lleva**: "un dato del simulador llega al navegador en tiempo real, sin tocar Timescale".

**Hito visible**: gráfica viva en el navegador.

## Módulo 7 — Criticidad, Redis y buffers

**Objetivo didáctico**: el modelo de criticidad y por qué importa.

**Qué se monta**:
- Redis en docker-compose.
- LKV (`SET lkv:<topic>`) alimentado por Telegraf.
- Redis Streams para topics buffered/critical.
- `realtime-service` lee la criticidad del registro y aplica la estrategia correspondiente.
- Telegraf reescribe a Redis en paralelo a Timescale.

**Lo que el alumno se lleva**: el porqué de los tres niveles, demostrado tirando el navegador y reconectando.

**Hito visible**: matar el navegador 30 segundos, reconectar, ver que las señales `buffered` y `critical` recuperan el hueco y las `standard` no.

## Módulo 8 — Eventos, alarmas y QoS 1

**Objetivo didáctico**: el camino de los eventos críticos y por qué se tratan distinto.

**Qué se monta**:
- `event-ingestor` en docker-compose, con sesión persistente y QoS 1.
- Tabla `events` poblándose.
- Widget de alarmas en el frontend.
- Botón en el simulator (vía API REST) para inyectar eventos manualmente.

**Lo que el alumno se lleva**: cómo viaja un evento crítico end-to-end, qué garantiza QoS 1, qué pasa si tiramos el ingestor mientras se publican eventos.

**Hito visible**: tirar el `event-ingestor`, disparar 5 eventos, levantarlo, ver que los 5 se persisten igualmente.

## Módulo 9 — Dashboards dinámicos con GridStack

**Objetivo didáctico**: la capa de visualización seria.

**Qué se monta**:
- GridStack en el frontend.
- Editor de dashboards (drag and drop).
- Persistencia de layouts en `dashboards` / `widgets`.
- Varios tipos de widget: gauge, line chart, alarm list, asset info.

**Lo que el alumno se lleva**: cómo el frontend lee del registro para "saber qué se puede mostrar" y deja al usuario componer sus vistas.

**Hito visible**: el alumno crea su propio dashboard sin tocar código.

## Módulo 10 — Drift y observabilidad

**Objetivo didáctico**: el sistema vigilándose a sí mismo.

**Qué se monta**:
- `meta-ingestor` poblando `meta_drift`.
- UI de admin para revisar drift y promocionar/ignorar.
- Métricas básicas de los servicios (Prometheus opcional).

**Lo que el alumno se lleva**: cómo se mantiene la integridad del registro a largo plazo.

## Módulo 11 — Preparación para LLMs (futuro)

Este lo dejo solo enunciado, no entra en el curso base pero la arquitectura ya está lista:
- Un nuevo servicio `llm-orchestrator` que usa la API REST como cualquier otro cliente.
- Tool de "list_namespace" leyendo del registro.
- Tool de "query_timeseries" leyendo de Timescale vía API.
- Conversión de respuestas LLM en acciones sobre dashboards (crear widget, etc.).

