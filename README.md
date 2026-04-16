# AeroNorth UNS — Plataforma Unified Namespace para IoT Industrial

## Qué es este proyecto

Una plataforma de datos industriales basada en el patrón **Unified Namespace (UNS)**, donde un broker MQTT actúa como bus central de datos. Todos los componentes (productores, bases de datos, servicios de visualización, futuros LLMs) se conectan al broker y se desacoplan entre sí.

El caso de uso de referencia es un **parque eólico** (AeroNorth Wind Farm, 6 aerogeneradores), pero el modelo de datos es genérico y aplicable a cualquier jerarquía ISA-95: fábricas, flotas navales, plantas de proceso, etc.

## Para qué sirve

- **Capturar señales** industriales (telemetría, eventos, metadatos) desde cualquier fuente.
- **Persistir** el histórico en una base de datos time-series (TimescaleDB).
- **Visualizar en tiempo real** con dashboards dinámicos configurables por el usuario.
- **Gestionar** el registro de señales desde una interfaz web (altas, bajas, criticidad).
- **Preparar el terreno** para integrar LLMs como consumidores inteligentes del UNS.

## Estructura del repositorio

```
aeronorth-uns/
├── CLAUDE.md                   # Índice técnico para Claude Code (inglés)
├── README.md                   # ← Estás aquí
├── docker-compose.yml          # Orquestación para desarrollo local
├── .env.example                # Variables de entorno de ejemplo
│
├── docs/
│   ├── en/                     # Documentación técnica (inglés, para Claude Code)
│   └── es/                     # Tutoriales y explicaciones (español, para ti)
│
└── services/
    ├── api-service/            # FastAPI: REST CRUD + Admin + Auth
    ├── sync-service/           # Sincroniza registro Postgres → MQTT $meta
    ├── realtime-service/       # Fan-out MQTT → WebSocket para navegadores
    ├── simulator/              # Simulador de datos eólicos (CSV → MQTT)
    ├── event-ingestor/         # Persiste eventos MQTT → Postgres
    ├── meta-ingestor/          # Detecta drift de metadatos
    └── frontend/               # React + GridStack: dashboards dinámicos
```

## Arquitectura en un vistazo

```
Productores                    Hub UNS              Consumidores
┌──────────────┐          ┌──────────────┐     ┌──────────────────────┐
│  simulator   │──MQTT──▶ │              │────▶│  telegraf → Timescale│
│  (Node-RED)  │          │  EMQX Broker │────▶│  event-ingestor → PG │
└──────────────┘          │              │────▶│  realtime-svc → WS   │
┌──────────────┐          │              │────▶│  meta-ingestor       │
│ sync-service │──MQTT──▶ │              │     └──────────────────────┘
│ (PG → $meta) │ retained └──────────────┘
└──────────────┘                                ┌──────────────────────┐
                                                │  api-service (REST)  │
       ┌───────────────────────────────────────▶│  ← frontend (React)  │
       │  Postgres (registro)                   └──────────────────────┘
       │  TimescaleDB (histórico)
       │  Redis (LKV + Streams)
```

## Stack tecnológico

| Capa              | Tecnología                                    |
|-------------------|-----------------------------------------------|
| Backend           | Python 3.12, FastAPI, SQLAlchemy async         |
| Auth              | fastapi-users (JWT)                            |
| Admin             | SQLAdmin                                       |
| Broker            | EMQX 5.x                                      |
| BBDD registro     | PostgreSQL 16                                  |
| BBDD time-series  | TimescaleDB (extensión sobre Postgres 16)      |
| Ingesta           | Telegraf                                       |
| Cache / buffer    | Redis 7.x (KV para LKV, Streams para buffer)  |
| Frontend          | React 18 + Vite + GridStack 10 + Plotly.js     |
| Orquestación      | Docker Compose                                 |

## Cómo empezar

El proyecto se construye de forma progresiva siguiendo los módulos del curso. Cada módulo tiene su tutorial en `docs/es/`:

1. **Módulo 1** — El broker y los primeros mensajes (`docs/es/10-modulo-01-broker.md`)
2. **Módulo 2** — El simulador y la jerarquía ISA-95 (`docs/es/11-modulo-02-simulator.md`)
3. **Módulo 3** — Persistencia con Telegraf y TimescaleDB (`docs/es/12-modulo-03-telegraf-timescale.md`)
4. **Módulo 4** — El registro UNS y el api-service (`docs/es/13-modulo-04-api-service.md`)
5. **Módulo 5** — El sync-service y LISTEN/NOTIFY (`docs/es/14-modulo-05-sync-service.md`)
6. **Módulo 6** — Frontend mínimo y realtime-service (`docs/es/15-modulo-06-frontend-realtime.md`)
7. **Módulo 7** — Criticidad, Redis y buffers (`docs/es/16-modulo-07-criticidad-redis.md`)
8. **Módulo 8** — Eventos, alarmas y QoS 1 (`docs/es/17-modulo-08-eventos-alarmas.md`)
9. **Módulo 9** — Dashboards dinámicos con GridStack (`docs/es/18-modulo-09-dashboards.md`)
10. **Módulo 10** — Drift y observabilidad (`docs/es/19-modulo-10-drift-observabilidad.md`)

## Principios de diseño

- **Postgres es la fuente de verdad** del registro. MQTT retained es solo el espejo.
- **El frontend nunca habla MQTT ni SQL directo.** Solo REST (api-service) y WebSocket (realtime-service).
- **La criticidad de la señal dicta el comportamiento** del buffer, no el nombre de la señal.
- **Cada servicio en su contenedor**, desacoplado, con responsabilidades claras.
- **Edge-Driven, Report by Exception, Lightweight**: los tres principios UNS que guían todo.

## Documentación

- **Para desarrollo con Claude Code**: empieza por `CLAUDE.md` y sigue a `docs/en/`.
- **Para entender el sistema**: empieza por `docs/es/00-introduccion.md`.
- **Para cada servicio**: cada carpeta en `services/` tiene su propio `README.md`.
