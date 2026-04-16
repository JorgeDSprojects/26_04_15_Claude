# 01 — Fundamentos de UNS e ISA-95

## El problema que resuelve UNS

Imagina una planta industrial donde el SCADA tiene sus datos, el MES los suyos, el ERP otros, el historian otro juego, y cada vez que alguien quiere cruzar datos de dos sistemas, un pobre ingeniero tiene que construir un conector punto a punto. Si tienes N sistemas, potencialmente tienes N×(N-1)/2 conexiones que mantener. Cada nueva integración es otro conector, otra fuente de verdad distinta, otro punto de fallo.

El UNS elimina ese problema creando un **único punto de encuentro**: un broker MQTT donde todos publican y todos consumen. Los productores publican una vez; los consumidores leen lo que necesitan. Nadie sabe (ni le importa) quién más está leyendo. Esto reduce las conexiones de N×(N-1)/2 a N (cada sistema solo habla con el broker).

## Los 5 principios fundamentales

### 1. Report by Exception
Solo publicas cuando hay un cambio. Si la temperatura del aceite lleva 10 minutos en 72°C, no mandas 60 mensajes diciendo "72, 72, 72..." — no mandas nada hasta que cambie. Esto reduce el tráfico drásticamente.

### 2. Edge-Driven
El dato se publica desde su origen, lo más cerca posible de la fuente. Un gateway en la planta lee el sensor y publica directamente al broker. No hay un servicio central que "pida" datos a los sensores (polling) — los sensores empujan (push).

### 3. Lightweight
Los mensajes son pequeños y frecuentes. Nada de enviar documentos XML de 50KB con toda la metadata cada vez que cambia una temperatura. El payload lleva solo lo imprescindible: valor, timestamp, calidad. El contexto lo da el topic.

### 4. Self-Describing
La estructura del topic describe el dato sin necesidad de documentación externa. Si ves `aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/temperature_bearing`, sabes exactamente qué es, de qué activo, de qué componente, y qué tipo de dato es (telemetría de medida).

### 5. Open Access
Cualquier sistema autorizado puede consumir cualquier dato. No hay APIs propietarias, no hay formatos cerrados. El broker es un espacio público (con auth) donde el dato está disponible para quien lo necesite.

## ISA-95: la jerarquía que da estructura al UNS

ISA-95 es un estándar internacional que define cómo organizar jerárquicamente los activos de una empresa industrial. El UNS usa esta jerarquía como base para sus topics MQTT.

### Los niveles

| Nivel ISA-95 | Qué representa | Ejemplo eólico | Ejemplo fábrica |
|---|---|---|---|
| Enterprise | La empresa | AeroNorth Energy | ACME Manufacturing |
| Site | Una instalación | Windfarm North | Planta León |
| Area | Una zona funcional | Sector A | Línea de envasado |
| Line | Un equipo principal | Turbine 03 | Prensa 1 |
| Cell | Un componente del equipo | Generator | Motor principal |

Estos niveles se convierten directamente en los segmentos del topic MQTT:

```
aeronorth/windfarm_north/sector_a/turbine_03/generator/measure/temperature
```

La jerarquía es flexible. No todas las empresas necesitan todos los niveles. Una fábrica pequeña podría tener solo Enterprise/Site/Line/Cell. Lo importante es que la estructura sea **consistente** dentro del despliegue.

## Los 4 tipos de namespace

Dentro de cada activo, los datos se organizan por tipo. Estos "namespaces" representan la naturaleza del dato:

### Descriptivo (`$meta`)
**¿Qué es este activo?** Atributos estáticos que cambian muy poco: modelo del equipo, fabricante, fecha de instalación, unidades de las señales.

Se publica como mensaje **retenido** (retained) en el broker, de modo que cualquier cliente nuevo que se conecte recibe inmediatamente la descripción sin esperar. La fuente de verdad es Postgres; el broker es solo el espejo.

Ejemplo: `.../$meta/rpm → {"unit": "rpm", "min": 0, "max": 25, "datatype": "float"}`

### Informativo (`measure`)
**¿Cómo está ahora?** Telemetría en tiempo real. Valores de sensores que cambian continuamente.

Se publica **sin retener** (para no saturar el broker de mensajes retenidos) y se persiste en TimescaleDB para histórico.

Ejemplo: `.../measure/rpm → {"val": 14.2, "ts": 1705400100500, "q": 1}`

### Operativo (`events`)
**¿Qué está pasando?** Eventos discretos: alarmas, paradas, cambios de estado, comandos.

Se publica con **QoS 1** (al menos una vez) porque perder una alarma es inaceptable. Se persiste en Postgres (no en TimescaleDB, porque los eventos tienen estructura relacional: reconocimiento, usuario que lo reconoció, etc.).

Ejemplo: `.../events/emergency_stop → {"event_type": "emergency_stop", "severity": "critical", ...}`

### Analítico (`$analytics`)
**¿Qué significa lo que está pasando?** Datos calculados por algoritmos o modelos de IA: KPIs, predicciones, tendencias.

Estos datos no vienen de sensores, sino de procesos que leen del UNS, calculan algo, y lo publican de vuelta al UNS. Así, el resultado de un modelo de IA está disponible para cualquier consumidor igual que la telemetría.

Ejemplo: `.../$analytics/efficiency → {"val": 0.89, "window": "1h"}`

## La distinción entre topic y payload

Este punto es fundamental y fuente habitual de confusión:

- **El topic** es la dirección. Es lo que usas para filtrar y enrutar. Los wildcards (`+`, `#`) operan sobre el topic.
- **El payload** es el contenido. Es lo que lleva el dato en sí.

**Nunca filtres por payload.** Si necesitas filtrar por tipo de señal, esa información tiene que estar en el topic (en el segmento de namespace: `measure`, `events`, `$meta`). Un consumidor se suscribe a `+/+/+/+/+/events/#` para recibir solo eventos — no se suscribe a `#` y luego descarta lo que no le interesa mirando dentro del payload.

## Report by Exception vs. polling

En una arquitectura clásica (SCADA tradicional), un servicio central va preguntando a cada sensor "¿cuánto vales?" cada X segundos. Esto es **polling**. Escala mal: si tienes 10.000 sensores y preguntas cada segundo, son 10.000 requests por segundo que tu servicio central tiene que gestionar.

En UNS con Report by Exception, el sensor (o su gateway) publica **solo cuando cambia**. Si no cambia, no hay tráfico. El broker distribuye solo lo que cambia a quien le interesa. Esto es **event-driven** y escala mucho mejor.

Nuestro simulador implementa ambas opciones para que puedas ver la diferencia, pero la configuración por defecto es Report by Exception.
