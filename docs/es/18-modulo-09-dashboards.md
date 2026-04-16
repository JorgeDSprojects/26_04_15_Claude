# Módulo 9 — Dashboards dinámicos con GridStack

## Objetivo

Convertir el frontend en una verdadera plataforma de visualización: dashboards con múltiples widgets que el usuario puede arrastrar, redimensionar, configurar, guardar y compartir. Sin tocar código.

**Tiempo estimado**: 4-5 horas.

## Conceptos que vas a manejar

- **GridStack.js**: librería de layouts drag-and-drop.
- **Persistencia de layouts** en JSONB en Postgres.
- **Widgets parametrizables**: chart, gauge, value card, alarm list, asset info.
- **Modo edición vs modo vista**.
- **Catálogo de señales** desde el frontend para que el usuario elija.

## Lo que vas a construir

- Tabla `dashboards` y `widgets` en Postgres (ya están en el esquema del módulo 4).
- Endpoints CRUD en `api-service` para dashboards y widgets.
- Página `DashboardEditor` en React con GridStack.
- Catálogo de tipos de widget.
- Modal de configuración por widget.

## Paso a paso

### 1. Endpoints REST de dashboards

`services/api-service/app/routers/dashboards.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.dependencies import get_db
from app.models.dashboard import Dashboard, Widget
from app.schemas.dashboard import (
    DashboardCreate, DashboardResponse,
    WidgetCreate, WidgetUpdate, WidgetResponse,
)

router = APIRouter(prefix="/api/v1/dashboards", tags=["dashboards"])

@router.get("", response_model=list[DashboardResponse])
async def list_dashboards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Dashboard))
    return result.scalars().all()

@router.get("/{id}", response_model=DashboardResponse)
async def get_dashboard(id: int, db: AsyncSession = Depends(get_db)):
    dash = await db.get(Dashboard, id)
    if not dash:
        raise HTTPException(404)
    return dash

@router.post("", status_code=201, response_model=DashboardResponse)
async def create_dashboard(body: DashboardCreate, db: AsyncSession = Depends(get_db)):
    dash = Dashboard(**body.model_dump())
    db.add(dash)
    await db.commit()
    await db.refresh(dash)
    return dash

# ... similar para PATCH, DELETE, y endpoints de widgets:
# POST /dashboards/{id}/widgets, PATCH /dashboards/{id}/widgets/{wid}, DELETE
```

Carga los widgets junto con el dashboard:

```python
from sqlalchemy.orm import selectinload

@router.get("/{id}", response_model=DashboardResponse)
async def get_dashboard(id: int, db: AsyncSession = Depends(get_db)):
    stmt = select(Dashboard).where(Dashboard.id == id).options(
        selectinload(Dashboard.widgets)
    )
    result = await db.execute(stmt)
    dash = result.scalar_one_or_none()
    if not dash:
        raise HTTPException(404)
    return dash
```

### 2. Instala GridStack en el frontend

```bash
cd services/frontend
npm install gridstack
```

### 3. Componente DashboardView (`src/pages/DashboardView.jsx`)

```javascript
import { useEffect, useRef, useState } from "react";
import { GridStack } from "gridstack";
import "gridstack/dist/gridstack.min.css";
import { LineChartWidget } from "../widgets/LineChartWidget";
import { GaugeWidget } from "../widgets/GaugeWidget";
import { ValueCardWidget } from "../widgets/ValueCardWidget";
import { AlarmListWidget } from "../widgets/AlarmListWidget";

const WIDGET_COMPONENTS = {
  line_chart: LineChartWidget,
  gauge: GaugeWidget,
  value_card: ValueCardWidget,
  alarm_list: AlarmListWidget,
};

export function DashboardView({ dashboardId, editable = false }) {
  const gridRef = useRef(null);
  const [widgets, setWidgets] = useState([]);

  useEffect(() => {
    fetch(`http://localhost:8000/api/v1/dashboards/${dashboardId}`)
      .then(r => r.json())
      .then(d => setWidgets(d.widgets));
  }, [dashboardId]);

  useEffect(() => {
    if (widgets.length === 0) return;

    const grid = GridStack.init({
      cellHeight: 70,
      margin: 10,
      float: true,
      disableDrag: !editable,
      disableResize: !editable,
    });
    gridRef.current = grid;

    if (editable) {
      grid.on("change", () => persistLayout(grid, dashboardId));
    }

    return () => grid.destroy(false);
  }, [widgets, editable, dashboardId]);

  return (
    <div className="grid-stack">
      {widgets.map(w => {
        const Comp = WIDGET_COMPONENTS[w.widget_type];
        if (!Comp) return null;
        return (
          <div
            key={w.id}
            className="grid-stack-item"
            gs-x={w.grid_x} gs-y={w.grid_y}
            gs-w={w.grid_w} gs-h={w.grid_h}
          >
            <div className="grid-stack-item-content">
              <Comp config={w.config} title={w.title} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

async function persistLayout(grid, dashboardId) {
  const items = grid.save(false);
  // items es un array con {x, y, w, h, id}
  // PATCH cada widget con su nueva posición
  for (const it of items) {
    await fetch(
      `http://localhost:8000/api/v1/dashboards/${dashboardId}/widgets/${it.id}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          grid_x: it.x, grid_y: it.y,
          grid_w: it.w, grid_h: it.h,
        }),
      }
    );
  }
}
```

### 4. Widgets concretos

`src/widgets/LineChartWidget.jsx`:

```javascript
import { useWebSocket } from "../hooks/useWebSocket";
import { useSignalMetadata } from "../hooks/useSignalMetadata";
import Plot from "react-plotly.js";

export function LineChartWidget({ config, title }) {
  // config = { signal_ids: [1, 2], time_range: "1h" }
  const signals = useSignalMetadata(config.signal_ids);
  const topics = signals.map(s => s.topic);
  const data = useWebSocket("ws://localhost:8001/ws", topics);

  const traces = signals.map(s => {
    const points = data[s.topic] || [];
    return {
      x: points.map(p => new Date(p.ts)),
      y: points.map(p => p.val),
      name: s.display_name,
      type: "scatter",
      mode: "lines",
    };
  });

  return (
    <Plot
      data={traces}
      layout={{ title, autosize: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
```

`src/widgets/ValueCardWidget.jsx`:

```javascript
export function ValueCardWidget({ config, title }) {
  const signal = useSignalMetadata([config.signal_id])[0];
  const data = useWebSocket("ws://localhost:8001/ws", signal ? [signal.topic] : []);
  const last = signal && (data[signal.topic] || []).slice(-1)[0];

  return (
    <div style={{ padding: 16, textAlign: "center" }}>
      <h3>{title}</h3>
      <div style={{ fontSize: 48, fontWeight: "bold" }}>
        {last ? last.val.toFixed(1) : "—"}
      </div>
      <div>{signal?.unit}</div>
    </div>
  );
}
```

`src/widgets/GaugeWidget.jsx`: usa `Plot` con `type: "indicator"` y `mode: "gauge"`.

`src/widgets/AlarmListWidget.jsx`: el que ya hicimos en el módulo 8.

### 5. Editor de dashboard

Página `src/pages/DashboardEditor.jsx`:

```javascript
import { useState, useEffect } from "react";
import { DashboardView } from "./DashboardView";
import { AddWidgetModal } from "../components/AddWidgetModal";

export function DashboardEditor({ dashboardId }) {
  const [showAdd, setShowAdd] = useState(false);

  return (
    <div>
      <header>
        <h1>Dashboard editor</h1>
        <button onClick={() => setShowAdd(true)}>+ Add widget</button>
      </header>
      <DashboardView dashboardId={dashboardId} editable />
      {showAdd && (
        <AddWidgetModal
          dashboardId={dashboardId}
          onClose={() => setShowAdd(false)}
        />
      )}
    </div>
  );
}
```

### 6. Modal "Add widget"

`src/components/AddWidgetModal.jsx`:

```javascript
import { useState, useEffect } from "react";

export function AddWidgetModal({ dashboardId, onClose }) {
  const [type, setType] = useState("line_chart");
  const [title, setTitle] = useState("");
  const [signals, setSignals] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);

  useEffect(() => {
    fetch("http://localhost:8000/api/v1/signals?enabled=true")
      .then(r => r.json())
      .then(setSignals);
  }, []);

  const submit = async () => {
    const config = type === "alarm_list"
      ? { max_items: 20 }
      : (type === "value_card" || type === "gauge")
        ? { signal_id: selectedIds[0] }
        : { signal_ids: selectedIds };

    await fetch(
      `http://localhost:8000/api/v1/dashboards/${dashboardId}/widgets`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          widget_type: type,
          title,
          config,
          grid_x: 0, grid_y: 0, grid_w: 4, grid_h: 4,
        }),
      }
    );
    onClose();
    window.location.reload();
  };

  return (
    <div className="modal">
      <h2>Add widget</h2>
      <label>Type:
        <select value={type} onChange={e => setType(e.target.value)}>
          <option value="line_chart">Line chart</option>
          <option value="value_card">Value card</option>
          <option value="gauge">Gauge</option>
          <option value="alarm_list">Alarm list</option>
        </select>
      </label>
      <label>Title:
        <input value={title} onChange={e => setTitle(e.target.value)} />
      </label>
      {type !== "alarm_list" && (
        <div>
          <label>Signals:</label>
          <select
            multiple={type === "line_chart"}
            value={selectedIds}
            onChange={e => setSelectedIds([...e.target.selectedOptions].map(o => +o.value))}
          >
            {signals.map(s => (
              <option key={s.id} value={s.id}>{s.display_name} ({s.topic})</option>
            ))}
          </select>
        </div>
      )}
      <button onClick={submit}>Add</button>
      <button onClick={onClose}>Cancel</button>
    </div>
  );
}
```

### 7. Routing básico

```javascript
// App.jsx
import { useState } from "react";
import { DashboardView } from "./pages/DashboardView";
import { DashboardEditor } from "./pages/DashboardEditor";

function App() {
  const [edit, setEdit] = useState(false);
  const dashboardId = 1;

  return (
    <div>
      <button onClick={() => setEdit(!edit)}>
        {edit ? "View mode" : "Edit mode"}
      </button>
      {edit
        ? <DashboardEditor dashboardId={dashboardId} />
        : <DashboardView dashboardId={dashboardId} />
      }
    </div>
  );
}
```

### 8. Crear el primer dashboard

```bash
# Crea un dashboard vacío
curl -X POST http://localhost:8000/api/v1/dashboards \
  -H "Content-Type: application/json" \
  -d '{"name": "Turbine 03 overview", "is_public": true}'
# Devuelve {"id": 1, ...}
```

Abre `http://localhost:5173`, click en "Edit mode", click en "+ Add widget", elige tipo y señales, "Add". Deberías ver el widget aparecer y poder arrastrarlo.

## Lo que has aprendido

- Cómo persistir layouts complejos en JSONB.
- Cómo usar GridStack para drag-and-drop.
- Cómo estructurar widgets parametrizables.
- Cómo separar el modo edición del modo vista.
- Cómo dejar al usuario componer dashboards sin tocar código.

## Comprobación final

- [ ] Puedes crear un dashboard.
- [ ] Puedes añadir widgets de varios tipos.
- [ ] Puedes mover y redimensionar widgets.
- [ ] El layout persiste al recargar.
- [ ] Los widgets reciben datos en tiempo real (WebSocket) y datos históricos (REST).

## Siguiente módulo

[Módulo 10 — Drift y observabilidad](19-modulo-10-drift-observabilidad.md)
