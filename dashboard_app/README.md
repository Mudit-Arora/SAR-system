# SAR Support System — Dashboard

The operator's live view for the Search-and-Rescue decision layer (see `../core_loop.md`).
It **reads** the Brain's probability map state and renders it — it never writes (single-writer
invariant preserved). Built with React + Vite + Tailwind.

## Run

```bash
npm install
npm run dev      # http://localhost:5173
```

```bash
npm run build    # type-check + production build to dist/
npm run preview  # serve the production build
```

## What's here

- **Probability map** (`ProbabilityMap.tsx`) — canvas heatmap (gaussian blobs → heat color
  scale) over a procedural terrain base, with flight path, drone, detection / searched markers,
  and the high-probability "located" candidate.
- **Search loop** (`SearchLoop.tsx`) — the 6-stage core loop (Build Prior → Plan Search →
  Detect → Update Map → Redirect → Notify).
- **Confidence to declare**, **live video feed** with detection box + HUD, **detections list**,
  **probability trend**, **map update summary**, and **voice & comms** (operator commands +
  subject broadcast).

## Wiring to the real Brain

All panels are driven by a single `MapState` object (`src/types.ts`). The mock lives in
`src/data/mockState.ts`. To go live, replace that import with a fetch from the Brain's read
model (e.g. a Redis read key or WebSocket) — the shapes already match the system contracts in
`../build_plan.md` / `../tech_and_sponsors.md`. `Data: Simulated` in the status bar flags the
current source.
