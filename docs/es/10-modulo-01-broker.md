# Módulo 1 — El broker y los primeros mensajes

## Objetivo

Levantar un broker MQTT (EMQX) en Docker, publicar tu primer mensaje y suscribirte para verlo llegar. Al terminar este módulo tendrás claro qué es un broker, qué es un topic, qué son los wildcards y qué es el QoS.

**Tiempo estimado**: 30-45 minutos.

## Conceptos que vas a manejar

- **Broker**: el "cartero" central. Recibe mensajes y los entrega a quien esté suscrito.
- **Topic**: la "dirección" del mensaje. Es una cadena con `/` como separador, tipo `aeronorth/turbine_03/measure/wind_speed`.
- **Publish (pub)**: enviar un mensaje a un topic.
- **Subscribe (sub)**: registrarse para recibir mensajes de un topic.
- **Wildcards**: `+` (un nivel) y `#` (multinivel) para suscribirte a patrones.
- **QoS**: nivel de garantía de entrega (0, 1 o 2).
- **Retained**: flag que hace que el broker guarde el último mensaje de un topic.

## Lo que vas a montar

Un único contenedor: `mqtt-broker` (EMQX). Nada más. Sin Postgres, sin Redis, sin código propio. Solo el broker y la línea de comandos.

## Paso a paso

### 1. Crea la estructura mínima del proyecto

```bash
mkdir -p aeronorth-uns
cd aeronorth-uns
```

### 2. Crea un `docker-compose.yml` mínimo

```yaml
services:
  mqtt-broker:
    image: emqx/emqx:5.7
    container_name: mqtt-broker
    ports:
      - "1883:1883"     # Puerto MQTT
      - "18083:18083"   # Dashboard web
    environment:
      EMQX_DASHBOARD__DEFAULT_PASSWORD: changeme
    volumes:
      - emqx-data:/opt/emqx/data
      - emqx-log:/opt/emqx/log

volumes:
  emqx-data:
  emqx-log:
```

### 3. Arranca el broker

```bash
docker compose up -d
```

Comprueba que está corriendo:

```bash
docker compose ps
docker compose logs -f mqtt-broker
```

Cuando veas un log tipo `EMQX 5.7.x is running now!`, está listo. Ctrl+C para salir de los logs.

### 4. Abre el dashboard web

Navega a `http://localhost:18083`. Usuario: `admin`, contraseña: `changeme`.

Tómate 2 minutos a explorar. Verás métricas (mensajes/segundo, conexiones), una sección de "Clients" (vacía por ahora), una de "Subscriptions" (vacía también) y una de "Topics".

### 5. Instala las herramientas de cliente MQTT

Necesitas `mosquitto_pub` y `mosquitto_sub` (vienen en el paquete `mosquitto-clients`):

```bash
# Ubuntu/Debian
sudo apt install mosquitto-clients

# macOS
brew install mosquitto

# Windows: descarga de https://mosquitto.org/download/
```

### 6. Tu primer suscriptor

Abre una terminal y suscríbete a todo:

```bash
mosquitto_sub -h localhost -p 1883 -t '#' -v
```

El `-t '#'` significa "todos los topics". El `-v` muestra el topic además del payload. Esta terminal se quedará escuchando.

### 7. Tu primer publicador

Abre **otra** terminal y publica un mensaje:

```bash
mosquitto_pub -h localhost -p 1883 -t 'hello/world' -m 'Hello UNS!'
```

Mira la primera terminal. Deberías ver:

```
hello/world Hello UNS!
```

¡Tu primer mensaje MQTT! Vuelve al dashboard `http://localhost:18083` y mira la sección de "Topics" — verás `hello/world` listado.

### 8. Prueba con jerarquía ISA-95

Publica algo más realista:

```bash
mosquitto_pub -h localhost -p 1883 \
  -t 'aeronorth/windfarm_north/sector_a/turbine_03/nacelle/measure/wind_speed' \
  -m '{"val": 12.3, "ts": 1705400100500, "q": 1}'
```

En la terminal del suscriptor lo ves llegar.

### 9. Prueba los wildcards

Detén el suscriptor anterior (Ctrl+C) y arranca uno con un patrón:

```bash
mosquitto_sub -h localhost -p 1883 -t '+/+/+/+/+/measure/#' -v
```

Esto se suscribe a cualquier topic que tenga `measure` en la sexta posición. Publica varios mensajes desde otra terminal:

```bash
mosquitto_pub -t 'aeronorth/windfarm_north/sector_a/turbine_03/rotor/measure/rpm' -m '{"val": 14.2}'
mosquitto_pub -t 'aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/active_power' -m '{"val": 850}'
mosquitto_pub -t 'aeronorth/windfarm_north/sector_a/turbine_03/controller/events/emergency_stop' -m '{"severity":"critical"}'
```

Los dos primeros llegan al suscriptor; el tercero (eventos) **no**, porque el patrón solo coge `measure/#`.

### 10. Prueba retained

Publica con `-r` (retained):

```bash
mosquitto_pub -h localhost -p 1883 \
  -t 'aeronorth/windfarm_north/sector_a/turbine_03/$meta/info' \
  -m '{"model": "GE-1.5SE", "rated_power_kw": 1500}' \
  -r
```

Ahora arranca un suscriptor **nuevo** (cierra el anterior con Ctrl+C):

```bash
mosquitto_sub -h localhost -p 1883 -t 'aeronorth/#' -v
```

Aunque el mensaje se publicó **antes** de suscribirte, el broker te lo entrega inmediatamente. Eso es retained: el broker guarda el último mensaje de ese topic y se lo da a cualquier nuevo suscriptor.

Para borrar un retained, publica un mensaje vacío con `-r`:

```bash
mosquitto_pub -t 'aeronorth/windfarm_north/sector_a/turbine_03/$meta/info' -m '' -r
```

### 11. Prueba QoS

QoS 0 (default): fire and forget.
QoS 1: el broker confirma la recepción.
QoS 2: handshake de 4 pasos, garantiza exactamente una vez (rara vez se usa).

```bash
mosquitto_pub -h localhost -p 1883 -t 'test/qos' -m 'qos1' -q 1
```

Por sí solo, no notas diferencia. La diferencia se ve cuando tiras el broker a la mitad y el cliente reintenta automáticamente.

## Lo que has aprendido

- Un broker MQTT es trivial de levantar en Docker.
- Los topics son cadenas jerárquicas separadas por `/`. La estructura no es obligatoria pero sí muy conveniente: usar ISA-95 te da contexto semántico.
- Los wildcards `+` y `#` te permiten suscribirte a patrones, no solo a topics individuales.
- El flag `retain` hace que el broker guarde el último mensaje de un topic. Útil para `$meta`, no para telemetría.
- El QoS 1 garantiza entrega; el QoS 0 no. La diferencia importa cuando hay desconexiones.

## Lo que NO has hecho todavía

- Persistir mensajes en una base de datos (módulo 3).
- Definir formalmente las señales en un registro (módulo 4).
- Visualizar nada en un navegador (módulo 6).

## Comprobación final

Antes de pasar al módulo 2, asegúrate de que:

- [ ] El contenedor `mqtt-broker` está corriendo.
- [ ] Puedes acceder al dashboard en `http://localhost:18083`.
- [ ] Puedes publicar y suscribirte desde la línea de comandos.
- [ ] Entiendes la diferencia entre `+` y `#`.
- [ ] Entiendes qué hace el flag `retain`.

## Siguiente módulo

[Módulo 2 — El simulador y la jerarquía ISA-95](11-modulo-02-simulator.md)
