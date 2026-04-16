# 99 — Glosario

## Términos UNS e industriales

**UNS (Unified Namespace)**: patrón arquitectónico donde un broker de mensajería actúa como bus central de datos. Todos los componentes publican y consumen de este bus, eliminando las integraciones punto a punto.

**ISA-95**: estándar internacional que define la jerarquía de activos industriales en niveles: Enterprise → Site → Area → Line → Cell. El UNS usa esta jerarquía como base para la estructura de topics MQTT.

**Report by Exception**: principio de publicación donde solo se envía un mensaje cuando el valor cambia. Si el sensor lee lo mismo 10 veces seguidas, no se publican 10 mensajes.

**Edge-Driven**: los datos se publican desde su origen (el sensor, el PLC, el gateway), no se "piden" desde un servicio central.

**Namespace (en contexto UNS)**: categoría semántica de un dato dentro del UNS. Hay cuatro tipos: descriptivo ($meta), informativo (measure), operativo (events) y analítico ($analytics).

**SCADA (Supervisory Control and Data Acquisition)**: sistema tradicional de supervisión y control industrial. El UNS no reemplaza al SCADA, pero puede complementarlo o, en nuevas instalaciones, servir como alternativa más moderna.

**Historian**: base de datos especializada en almacenar series temporales de datos industriales. En nuestro caso, TimescaleDB cumple esta función.

## Términos MQTT

**Broker**: servidor central de mensajería MQTT. Recibe mensajes de los publicadores y los distribuye a los suscriptores. En nuestro caso, EMQX.

**Topic**: la "dirección" a la que se publica un mensaje. Usa `/` como separador de niveles. Ejemplo: `aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm`.

**Payload**: el contenido del mensaje. En nuestro caso, siempre JSON.

**Publish (pub)**: enviar un mensaje a un topic.

**Subscribe (sub)**: registrarse para recibir mensajes de un topic o patrón de topics.

**Wildcard +**: comodín de un solo nivel. `+/+/+/+/+/measure/#` coincide con cualquier combinación de los primeros 5 niveles, seguida de `measure` y cualquier cosa después.

**Wildcard #**: comodín multinivel. Solo puede ir al final. `aeronorth/#` coincide con todo lo que empiece por `aeronorth/`.

**QoS (Quality of Service)**: nivel de garantía de entrega. QoS 0 = fire and forget (puede perderse). QoS 1 = al menos una vez (puede duplicarse). QoS 2 = exactamente una vez (lento, rara vez usado en IoT).

**Retain (retained message)**: flag que indica al broker que guarde el último mensaje en un topic. Cuando un nuevo cliente se suscribe, recibe inmediatamente el mensaje retenido sin esperar a la siguiente publicación.

**Persistent session (sesión persistente)**: el broker guarda los mensajes destinados a un cliente desconectado y se los entrega cuando vuelve. Requiere QoS ≥ 1.

## Términos de la plataforma

**LKV (Last Known Value)**: el último valor recibido para cada señal, almacenado en Redis. Se usa para que un widget nuevo pueda mostrar un valor inmediatamente sin esperar al próximo mensaje MQTT.

**Criticality (criticidad)**: atributo de cada señal que determina cómo se gestiona su entrega: standard (sin buffer), buffered (con catch-up via Redis Streams), critical (QoS 1 + buffer grande).

**Drift**: situación donde el broker contiene metadatos ($meta) de señales que no están registradas en la base de datos. Indica que alguien está publicando señales "no oficiales".

**Sync-service**: servicio que mantiene sincronizados el registro de Postgres y los mensajes $meta retained del broker. Postgres → MQTT, no al revés.

**Realtime-service**: servicio que hace de puente entre MQTT y los navegadores web via WebSocket. El navegador nunca habla MQTT directamente.

**GridStack**: librería JavaScript que permite crear layouts de dashboard con drag and drop. Cada widget se puede mover, redimensionar y configurar.

## Términos técnicos generales

**LISTEN/NOTIFY**: mecanismo nativo de PostgreSQL para notificaciones en tiempo real. Un proceso hace `LISTEN canal` y otro hace `NOTIFY canal, 'datos'`. No requiere polling.

**Hypertable**: tabla especial de TimescaleDB optimizada para datos de series temporales. Particiona automáticamente por tiempo.

**Redis Streams**: estructura de datos de Redis diseñada para logs y colas de mensajes. Soporta grupos de consumidores y lectura desde un punto específico (ideal para catch-up tras desconexión).

**asyncio**: módulo de Python para programación asíncrona. Permite manejar miles de conexiones concurrentes sin crear un hilo por cada una.

**Alembic**: herramienta de migraciones de esquema de base de datos para SQLAlchemy. Permite versionar los cambios en las tablas.

**SQLAdmin**: librería que genera un panel de administración web (tipo Django admin) sobre modelos SQLAlchemy + FastAPI.

**fastapi-users**: librería que añade registro, login, JWT y gestión de usuarios a FastAPI sin escribir el código desde cero.
