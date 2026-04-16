# 03 — El caso eólico AeroNorth

## Por qué un parque eólico

Un aerogenerador es una máquina sorprendentemente completa desde el punto de vista de datos industriales. Tiene componentes mecánicos (rotor, multiplicadora), eléctricos (generador, conexión a red), de control (pitch, yaw), y medioambientales (sensores de viento y temperatura). Genera telemetría continua, eventos discretos, y KPIs derivados. Todo lo que necesitamos para cubrir los cuatro tipos de namespace UNS.

Además, hay datasets públicos de SCADA eólico (Kaggle) que nos dan datos reales con los que alimentar el simulador, en lugar de inventar números aleatorios.

## La planta

| Atributo | Valor |
|---|---|
| Nombre | AeroNorth Wind Farm |
| Operador | AeroNorth Energy |
| Ubicación | Costa norte de España (ficticia) |
| Sectores | 2 (sector_a, sector_b) |
| Turbinas | 6 (3 por sector) |
| Señales por turbina | 22 |
| Total señales | 132 |
| Tipos de evento | 7 |
| Frecuencia de telemetría | 10 segundos (configurable) |

## Jerarquía ISA-95 aplicada

```
AeroNorth Energy          (Enterprise)
  └── Windfarm North      (Site)
        ├── Sector A      (Area)
        │     ├── Turbine 01   (Line)
        │     ├── Turbine 02   (Line)
        │     └── Turbine 03   (Line)
        └── Sector B      (Area)
              ├── Turbine 04   (Line)
              ├── Turbine 05   (Line)
              └── Turbine 06   (Line)
```

Cada turbina tiene 6 componentes (Cell):

| Componente | Descripción |
|---|---|
| rotor | Rotor y palas |
| nacelle | Góndola: carcasa superior con sensores ambientales |
| generator | Generador eléctrico |
| gearbox | Multiplicadora (caja de engranajes) |
| tower | Torre de soporte |
| controller | Sistema de control y estado operativo |

## Catálogo de señales

### Rotor (2 señales)

| Señal | Unidad | Tipo dato | Criticidad | Justificación criticidad |
|---|---|---|---|---|
| rpm | rpm | float | buffered | Indicador clave del comportamiento mecánico |
| pitch_angle | deg | float | standard | Cambios lentos, perder muestras no es grave |

### Nacelle (5 señales)

| Señal | Unidad | Tipo dato | Criticidad | Justificación |
|---|---|---|---|---|
| wind_speed | m/s | float | buffered | Variable principal del proceso eólico |
| wind_direction | deg | float | standard | Cambios graduales |
| yaw_angle | deg | float | standard | Posición de giro de la góndola |
| ambient_temperature | °C | float | standard | Cambia lentamente |
| vibration_level | mm/s | float | buffered | Indicador temprano de problemas mecánicos |

### Generator (7 señales)

| Señal | Unidad | Tipo dato | Criticidad | Justificación |
|---|---|---|---|---|
| active_power | kW | float | buffered | Métrica de negocio principal |
| reactive_power | kVAr | float | standard | Complementaria |
| rpm | rpm | float | standard | Redundante con el rotor RPM × ratio |
| temperature_winding_u | °C | float | buffered | Sobretemperatura = riesgo de avería |
| temperature_winding_v | °C | float | buffered | Idem |
| temperature_winding_w | °C | float | buffered | Idem |
| temperature_bearing | °C | float | buffered | Cojinete caliente = problema mecánico |

### Gearbox (3 señales)

| Señal | Unidad | Tipo dato | Criticidad | Justificación |
|---|---|---|---|---|
| oil_temperature | °C | float | buffered | Degradación del lubricante |
| oil_pressure | bar | float | buffered | Presión baja = alerta inmediata |
| vibration_level | mm/s | float | buffered | Desgaste de engranajes |

### Tower (2 señales)

| Señal | Unidad | Tipo dato | Criticidad | Justificación |
|---|---|---|---|---|
| top_acceleration_x | m/s² | float | standard | Medida estructural, frecuencia baja |
| top_acceleration_y | m/s² | float | standard | Idem |

### Controller (3 señales)

| Señal | Unidad | Tipo dato | Criticidad | Justificación |
|---|---|---|---|---|
| operational_state | — | enum | critical | RUN/STOP/FAULT/MAINTENANCE: perder transiciones es inadmisible |
| grid_connection | — | bool | critical | Conexión/desconexión de red: evento de seguridad |
| total_energy_produced | kWh | float | standard | KPI acumulado, se reconstruye con el siguiente valor |

### Resumen por criticidad

| Criticidad | Cantidad | Porcentaje | Ejemplos |
|---|---|---|---|
| standard | 9 | 41% | temperaturas ambiente, ángulos, aceleraciones |
| buffered | 11 | 50% | potencia, viento, RPM, temperaturas críticas, presiones |
| critical | 2 | 9% | estado operativo, conexión a red |

## Eventos

Todos los eventos se publican con criticidad `critical` y QoS 1.

| Evento | Trigger | Severidad | Datos adicionales |
|---|---|---|---|
| emergency_stop | Parada de emergencia activada | critical | trigger (manual/automático) |
| high_wind_cutoff | Viento > 25 m/s durante 10+ segundos | critical | velocidad del viento al cortar |
| grid_loss | Pérdida de conexión a la red eléctrica | critical | último estado conocido |
| overtemperature | Cualquier temperatura > umbral configurable | error | señal que disparó, valor, umbral |
| low_oil_pressure | Presión de aceite < umbral | error | presión actual, umbral |
| maintenance_started | Entrada en modo mantenimiento | info | usuario que inició |
| maintenance_ended | Salida de modo mantenimiento | info | duración total |

## El simulador

El simulador no es solo un reproductor de CSV. Es una herramienta didáctica con tres modos:

### Modo CSV (por defecto)
Lee el dataset Kaggle fila por fila, mapeando cada columna a la señal correspondiente, y publica a intervalo configurable (10s por defecto). Las señales que no están en el CSV (temperaturas de cojinetes, vibraciones, etc.) se generan sintéticamente con ruido gaussiano sobre valores base realistas.

### Modo sintético
Genera todas las señales sintéticamente sin CSV. Útil para pruebas rápidas o para escenarios que el CSV no cubre.

### Inyección de eventos
Desde el frontend (o vía API REST del simulador), puedes disparar eventos manualmente. Ejemplo: click en "Emergency stop on Turbine 02" → el simulador publica el evento → el dashboard lo muestra en tiempo real. Esto permite demostrar el flujo completo de eventos durante el curso sin esperar a que un evento "natural" ocurra.

## Lo que NO modela este caso

- **Comunicaciones edge ↔ cloud**: todo corre en local, no hay latencia de red real.
- **Protocolos industriales**: no hay Modbus ni OPC-UA reales. El simulador publica MQTT directamente. Los campos `protocol` y `connection_config` en el registro están preparados para el futuro pero no se ejecutan.
- **Lógica de control**: no hay pitch control real, ni yaw control, ni curtailment. El simulador genera valores; no hay feedback loop.
- **Multi-site**: solo un parque. Escalar a varios parques es trivial (nuevos assets bajo el enterprise), pero no está en el alcance del curso.
