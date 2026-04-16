# 04 — El modelo de criticidad

## El problema

No todas las señales son igual de importantes. Perder 3 muestras de la temperatura ambiente mientras un usuario refresca el navegador es perfectamente aceptable — en 30 segundos llega la siguiente y el gráfico sigue. Pero perder una alarma de parada de emergencia porque el servicio WebSocket estaba reiniciándose es inaceptable.

El modelo de criticidad resuelve esto: cada señal tiene asignado un nivel que dicta cómo se trata su entrega, buffering y recuperación ante desconexiones.

## Los tres niveles

### Standard — "me importa el valor actual, no la continuidad"

Pensado para señales donde lo que importa es el último valor, no tener un historial perfecto segundo a segundo en el dashboard.

**Qué pasa en la práctica:**
- Los mensajes viajan por MQTT sin garantía de entrega (QoS 0).
- Cuando el navegador está conectado, recibe los datos en vivo sin problema.
- Si el navegador se desconecta (cierre de pestaña, pérdida de red, recarga), se pierden los mensajes que llegan durante ese tiempo.
- Al reconectar, el dashboard carga el **último valor conocido** de Redis y sigue desde ahí. No hay "catch-up" del hueco.
- El buffer en memoria del servidor WebSocket tiene capacidad limitada (100 mensajes). Si el cliente se atasca (conexión lenta), los mensajes más antiguos se descartan.

**Analogía**: es como una radio en directo. Si apagas la radio 5 minutos y la vuelves a encender, te pierdes lo que dijeron. Y no pasa nada.

**Señales típicas**: temperatura ambiente, ángulo de yaw, aceleración de torre, potencia reactiva.

### Buffered — "quiero continuidad en el dashboard"

Pensado para señales donde los gráficos de tendencia importan y un hueco en la serie es visible y molesto.

**Qué pasa en la práctica:**
- Los mensajes viajan por MQTT con QoS 0 (igual que standard — la diferencia está en la capa de aplicación, no en el transporte).
- Cada mensaje se escribe en un **Redis Stream** (además del LKV). El stream mantiene los últimos ~1000 mensajes por señal.
- Cada cliente WebSocket tiene un "puntero" en el stream (el último mensaje que leyó).
- Si el navegador se desconecta y vuelve, el servidor lee del stream todos los mensajes desde el último puntero y se los envía. El gráfico se rellena sin huecos.
- Si la desconexión dura más de lo que cubre el buffer (~2.7 horas a 10s/muestra), los mensajes más antiguos se pierden. Es un compromiso razonable.

**Analogía**: es como un podcast. Si pierdes conexión 5 minutos, cuando vuelves puedes rebobinar y escuchar lo que te perdiste. Pero no puedes rebobinar indefinidamente.

**Señales típicas**: velocidad del viento, potencia activa, RPM del rotor, temperaturas de cojinetes y bobinados, presión de aceite, vibración.

### Critical — "no puedo perder ni un solo mensaje"

Pensado para eventos y señales de estado donde cada transición importa.

**Qué pasa en la práctica:**
- Los mensajes viajan por MQTT con **QoS 1** (al menos una vez). El broker confirma la recepción y, si el consumidor está caído, guarda los mensajes hasta que vuelva (sesión persistente).
- Se usa Redis Stream con buffer mayor (~10000 mensajes).
- El `event-ingestor` tiene sesión persistente con el broker: si se reinicia, no pierde nada.
- Los consumidores deben ser **idempotentes** (preparados para recibir duplicados, porque QoS 1 es "al menos una vez", no "exactamente una vez").

**Analogía**: es como un correo certificado. El cartero te lo entrega en mano y espera tu firma. Si no estás, lo guarda y vuelve mañana.

**Señales típicas**: estado operativo (RUN/STOP/FAULT), conexión a red, y todos los eventos (alarmas, paradas, mantenimientos).

## Por qué tres niveles y no más

Podríamos definir 5 niveles, 7 niveles, criticidad por señal y por consumidor... pero cada nivel adicional añade complejidad al `realtime-service`, consume más recursos de Redis, y hace más difícil de entender el sistema. Tres niveles cubren el 99% de los casos industriales reales:

1. "No me importa perder muestras" → standard
2. "Quiero continuidad pero no es vida o muerte" → buffered
3. "Es un evento, no puedo perderlo" → critical

Si algún día aparece un caso que no encaja, lo discutimos. Pero no lo inventamos por anticipado.

## Cómo se configura

Desde la interfaz web de administración:

1. Navega a la gestión de señales.
2. Selecciona una señal (o la creas nueva).
3. En el campo "Criticality", elige entre Standard, Buffered o Critical.
4. Guarda.

El cambio se propaga automáticamente:
- `api-service` actualiza Postgres.
- Postgres dispara un NOTIFY.
- `sync-service` recibe el NOTIFY y republica el `$meta` de esa señal con la criticidad actualizada.
- `realtime-service` recibe el `$meta` actualizado y ajusta su estrategia de buffer para esa señal.

**No hace falta reiniciar nada.** Todo es dinámico.

## Impacto en recursos

| Recurso | Standard | Buffered | Critical |
|---|---|---|---|
| RAM del servidor WS | ~100 msgs × tamaño payload | Mínima (Redis gestiona) | Mínima (Redis gestiona) |
| Escrituras Redis/msg | 1 (SET LKV) | 2 (SET LKV + XADD) | 2 (SET LKV + XADD) |
| Almacenamiento Redis | ~1 KB por señal | ~1 MB por señal (1000 msgs) | ~10 MB por señal (10000 msgs) |
| Carga del broker | Baja (QoS 0) | Baja (QoS 0) | Mayor (QoS 1, ACKs) |

Con 132 señales (caso AeroNorth): 9 standard + 11 buffered + 2 critical por turbina, × 6 turbinas:
- Redis LKV: ~132 KB (todas las señales)
- Redis Streams: ~66 MB buffered + ~12 MB critical ≈ **~78 MB de Redis** en total
- Perfectamente manejable para un despliegue en un solo host.

## La tensión entre "no perder nada" y "tiempo real"

Vale la pena entender que garantizar la entrega y mantener baja latencia son objetivos en tensión. QoS 1 añade un roundtrip de ACK entre broker y consumidor. Redis Streams añaden una escritura y una lectura extra por mensaje. Para 132 señales esto es negligible, pero para 100.000 señales a 1 msg/segundo la cosa cambia.

Por eso no ponemos todo en `critical`: sería desperdiciar recursos en señales donde no aporta valor. La criticidad se asigna con criterio, no con miedo.
