# 00 — Introducción al proyecto AeroNorth UNS

## Qué vas a construir

Una plataforma de datos industriales completa que captura señales de un parque eólico, las persiste en bases de datos, y las muestra en tiempo real en dashboards dinámicos configurables desde el navegador.

La plataforma sigue el patrón **Unified Namespace (UNS)**: un broker MQTT actúa como bus central donde todos los datos se publican y consumen. Ningún componente conoce a los demás — solo conocen el broker y la estructura de topics.

## Por qué este enfoque

En la industria real, los datos están fragmentados: el SCADA tiene los suyos, el MES los suyos, el ERP otros, y cada integración nueva es un conector punto a punto que hay que mantener. El UNS resuelve esto creando un "bus de planta" unificado. Un productor publica una vez; todos los consumidores (bases de datos, dashboards, modelos de IA) leen del mismo sitio.

Esto es lo que vas a aprender a construir, paso a paso.

## El caso de uso: parque eólico AeroNorth

Hemos elegido un parque eólico ficticio como caso de referencia porque:

- Tiene una **jerarquía clara** (empresa → parque → sector → turbina → componente) que mapea perfectamente a ISA-95.
- Genera **señales variadas**: temperaturas, velocidades, potencias, ángulos, estados — perfecto para demostrar distintos tipos de datos y criticidades.
- Produce **eventos discretos** (paradas de emergencia, cortes por viento, alarmas) que necesitan un tratamiento diferente a la telemetría continua.
- Hay **datasets públicos** (Kaggle SCADA) que podemos usar como base para el simulador.

Pero el modelo de datos es **genérico**. Las tablas no se llaman `turbines` o `blades`, sino `assets`, `signals`, `asset_types`. La misma plataforma podría gestionar una fábrica, una flota naval o una planta química cambiando solo los datos de configuración.

## La planta AeroNorth

- **Nombre**: AeroNorth Wind Farm
- **Ubicación ficticia**: costa norte de España
- **Operador**: AeroNorth Energy
- **6 aerogeneradores** repartidos en 2 sectores (3 por sector)
- **22 señales por turbina** (132 en total)
- **7 tipos de eventos** por turbina (alarmas, paradas, cambios de estado)

## Qué vas a aprender

El curso tiene **10 módulos progresivos**. La filosofía es "ver el dato fluir lo antes posible" — no vas a pasar tres módulos escribiendo SQL sin ver un mensaje moverse.

1. **Módulo 1**: levantar un broker MQTT y ver mensajes moverse en la terminal.
2. **Módulo 2**: montar un simulador que publique datos de una turbina con topics ISA-95.
3. **Módulo 3**: persistir la telemetría en TimescaleDB con Telegraf.
4. **Módulo 4**: crear el registro de señales en Postgres con una API REST (FastAPI).
5. **Módulo 5**: sincronizar el registro con el broker automáticamente (sync-service).
6. **Módulo 6**: mostrar datos en tiempo real en el navegador (React + WebSocket).
7. **Módulo 7**: implementar los tres niveles de criticidad con Redis.
8. **Módulo 8**: gestionar eventos y alarmas con QoS 1.
9. **Módulo 9**: dashboards dinámicos con GridStack (drag and drop).
10. **Módulo 10**: drift detection y observabilidad.

## Prerrequisitos

- Docker y Docker Compose instalados.
- Conocimiento básico de Python (asyncio no es necesario, lo aprendes aquí).
- Conocimiento básico de MQTT (publicar, suscribir, topics — si vienes de cero, el módulo 1 te cubre).
- Conocimiento básico de React (componentes, hooks — no necesitas ser experto).
- Una terminal y un editor de código.

## Cómo usar este repositorio

- **Para entender el sistema**: lee los documentos en `docs/es/` (donde estás ahora), empezando por este fichero.
- **Para desarrollar con Claude Code**: abre `CLAUDE.md` en la raíz del repo. Claude Code lee la documentación técnica en `docs/en/` (en inglés, densa, estructurada).
- **Para cada servicio**: cada carpeta en `services/` tiene su propio `README.md` con instrucciones específicas.

## Stack tecnológico

| Qué                | Tecnología                              |
|--------------------|-----------------------------------------|
| Broker MQTT        | EMQX 5.x                                |
| BBDD de registro   | PostgreSQL 16                            |
| BBDD time-series   | TimescaleDB                              |
| Cache y buffer     | Redis 7.x                                |
| Ingesta telemetría | Telegraf                                 |
| API y admin        | FastAPI + SQLAlchemy + SQLAdmin           |
| Auth               | fastapi-users (JWT)                      |
| Tiempo real        | FastAPI WebSockets                       |
| Frontend           | React 18 + Vite + GridStack + Plotly.js  |
| Orquestación       | Docker Compose                           |

## Principios de diseño que no negociamos

1. **Postgres es la fuente de verdad** del registro. MQTT retained es el espejo, nunca la fuente primaria.
2. **El frontend nunca habla MQTT ni SQL.** Solo REST y WebSocket, siempre a través de servicios intermedios.
3. **La criticidad de la señal dicta el comportamiento** del sistema, no el nombre de la señal.
4. **Cada servicio en su contenedor**, desacoplado, con responsabilidades claras y bien documentadas.
5. **Edge-Driven, Report by Exception, Lightweight**: los tres principios UNS que guían todas las decisiones.
