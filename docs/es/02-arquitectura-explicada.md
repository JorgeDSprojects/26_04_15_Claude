# 02 — La arquitectura explicada

## La visión general

El sistema tiene 7 servicios propios, 4 servicios de infraestructura (broker, BBDD, cache) y un frontend. Todo corre en Docker Compose. Cada servicio tiene una responsabilidad clara y no se mete en la de los demás.

La regla de oro: **el broker MQTT es el corazón, Postgres es el cerebro, el frontend es la cara.** El broker mueve datos, Postgres sabe qué datos existen, y el frontend te los enseña.

## Los planos de la arquitectura

### Plano 1 — Productores

Son los que meten datos en el sistema.

**`simulator`** (Python): lee un CSV con datos SCADA de turbinas eólicas y los publica en el broker como si fueran datos en tiempo real. También puede generar eventos sintéticos (paradas, alarmas) para demos. Es la pieza que simula el "edge" industrial.

**`sync-service`** (Python): lee el registro de señales de Postgres y lo publica en el broker como mensajes `$meta` retenidos. Es el puente entre "lo que la base de datos dice que existe" y "lo que el broker muestra que existe". Escucha cambios en Postgres en tiempo real vía LISTEN/NOTIFY — si das de alta una señal nueva desde la web, en milisegundos aparece en el broker.

### Plano 2 — El broker (EMQX)

El hub central. Todo el mundo publica aquí y todo el mundo lee de aquí. EMQX es un broker MQTT empresarial open-source que soporta millones de conexiones, persistencia, ACLs por topic y un dashboard de administración en el puerto 18083.

El broker NO procesa datos. NO transforma nada. Solo recibe y distribuye. Es un cartero: le da igual si el sobre contiene una factura o una carta de amor.

### Plano 3 — Consumidores de persistencia

Son los que convierten datos efímeros (mensajes MQTT) en datos permanentes (filas en base de datos).

**`telegraf`**: agente de ingesta configurado (no hay código, solo un fichero de configuración). Se suscribe a toda la telemetría informativa (`measure/#`) y la escribe en TimescaleDB. En paralelo, actualiza el "último valor conocido" (LKV) en Redis para cada señal.

**`event-ingestor`** (Python): se suscribe a los eventos operativos (`events/#`) con QoS 1 y sesión persistente. Si este servicio se cae, el broker le guarda los mensajes hasta que vuelva. Los eventos se escriben en Postgres (no en Timescale, porque tienen estructura relacional).

**`meta-ingestor`** (Python): se suscribe a los metadatos (`$meta/#`) y compara lo que llega con lo que hay en el registro. Si detecta un `$meta` de una señal que no está registrada, lo guarda en una tabla de "drift" para que un admin lo revise. Es el vigilante del sistema.

### Plano 4 — Almacenamiento

**PostgreSQL** (registro): la fuente de verdad. Aquí viven las tablas de activos, señales, tipos, eventos, dashboards, usuarios. Solo `api-service` escribe aquí (y `event-ingestor` en la tabla de eventos). Nadie más toca esta base de datos directamente.

**TimescaleDB**: una extensión de Postgres optimizada para datos de series temporales. Aquí vive la telemetría histórica. Solo Telegraf escribe y solo `api-service` lee (para responder a consultas históricas del frontend).

**Redis**: doble función. Como **diccionario de último valor** (LKV): almacena el valor más reciente de cada señal para que un widget nuevo pueda mostrarlo inmediatamente sin consultar la base de datos. Como **buffer de continuidad** (Streams): para las señales con criticidad `buffered` o `critical`, almacena un historial corto que permite al cliente reconectar y recuperar lo que se perdió.

### Plano 5 — API de dominio

**`api-service`** (FastAPI): es la única puerta al mundo exterior para todo lo que no sea tiempo real. Expone:
- CRUD de activos y señales (dar de alta, modificar, borrar)
- Consultas históricas de time-series
- Gestión de dashboards y widgets
- Autenticación y autorización (JWT con fastapi-users)
- Panel de administración web (SQLAdmin en `/admin`)

**Regla absoluta**: el frontend NUNCA toca las bases de datos directamente. Todo pasa por esta API.

### Plano 6 — Tiempo real hacia el navegador

**`realtime-service`** (FastAPI con WebSockets): se suscribe al broker MQTT y hace fan-out a los navegadores conectados. Cada navegador abre un WebSocket y dice "quiero estos topics". El servicio le envía los datos en tiempo real, aplicando la estrategia de buffer que corresponda según la criticidad de cada señal.

**¿Por qué no conectar el navegador directamente al broker?** Porque perderías el control sobre autenticación, filtrado por permisos, y throttling. El `realtime-service` es la frontera de seguridad entre el broker industrial y el mundo web.

### Plano 7 — Frontend

**React + Vite + GridStack + Plotly.js**: dashboards dinámicos donde el usuario arrastra widgets, elige qué señales mostrar, y compone sus propias vistas. También incluye la parte de administración: gestión de señales, configuración de criticidad, revisión de drift, gestión de usuarios.

El frontend habla con dos servicios: REST con `api-service` (para configuración e históricos) y WebSocket con `realtime-service` (para datos en vivo).

## Flujo típico de un dato

Para que todo esto sea concreto, seguimos un dato desde que nace hasta que aparece en una pantalla:

1. El **simulador** lee del CSV que la velocidad del viento es 12.3 m/s.
2. Publica en EMQX: topic `aeronorth/.../nacelle/measure/wind_speed`, payload `{"val": 12.3, "ts": ..., "q": 1}`.
3. **EMQX** distribuye el mensaje a todos los suscriptores.
4. **Telegraf** lo recibe, lo escribe en TimescaleDB y actualiza el LKV en Redis.
5. **`realtime-service`** lo recibe, mira la criticidad de esa señal (buffered), lo mete en un Redis Stream y lo envía por WebSocket a los navegadores que lo estén pidiendo.
6. El **frontend** lo recibe por WebSocket y actualiza el gráfico de viento en tiempo real.

Todo eso ocurre en milisegundos. Y si el navegador se desconecta 30 segundos y vuelve, el `realtime-service` le envía los datos que se perdió leyendo del Redis Stream.

## Lo que la arquitectura NO es

- **No es un SCADA de producción.** Es una plataforma formativa y un MVP.
- **No es multi-tenant.** Un despliegue = una organización.
- **No corre en edge.** Todo corre en un único host Docker.
- **No está optimizada para millones de señales.** Funciona bien con cientos, que es más que suficiente para aprender y para MVPs.
