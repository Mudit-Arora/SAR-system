// Type contracts for the SAR dashboard.
// These mirror the system's real state shapes (see core_loop.md / build_plan.md):
// the Brain owns MapState (single writer); the dashboard only reads it.

export type LoopStepStatus = 'done' | 'live' | 'next'

export interface LoopStep {
  id: number
  label: string
  status: LoopStepStatus
}

// A single ground-referenced detection emitted by Detector -> GeoReferencer.
export interface Detection {
  id: string
  timestamp: string // HH:MM:SS
  confidence: number // 0..1
  persistence: { seen: number; of: number } // e.g. 5/5 frames
  label: string // "LIKELY PERSON" | "PERSON" | ...
  distanceM: number // distance from drone, meters
  isPrimary: boolean // the confident + repeated "located" candidate
  // normalized map position 0..1 (x right, y down) for the map overlay
  pos: { x: number; y: number }
  thumbnailHue: number // placeholder thumbnail tint
}

// A node along the scripted flight path / a waypoint marker on the map.
export type WaypointKind = 'detection' | 'searched' | 'high-prob'
export interface Waypoint {
  id: string
  kind: WaypointKind
  pos: { x: number; y: number }
}

export interface MissionStats {
  searchTime: string
  areaCoveredKm2: number
  flightDistanceKm: number
  detections: number
  personsFound: number
}

export interface MapLayer {
  id: string
  label: string
  enabled: boolean
}

export interface ProbabilityPoint {
  t: string // HH:MM
  mass: number // top-5% probability mass concentration, 0..100
}

export interface OperatorCommand {
  text: string
  time: string
}

// The serializable read-model the dashboard consumes.
export interface MapState {
  missionName: string
  region: string
  startedAt: string
  loop: LoopStep[]
  confidenceToDeclare: number // 0..100
  declareThreshold: number // 0..100
  stats: MissionStats
  layers: MapLayer[]
  detections: Detection[]
  waypoints: Waypoint[]
  // normalized path the drone has flown / will fly
  flightPath: { x: number; y: number }[]
  dronePos: { x: number; y: number }
  // hot spots for the probability heatmap (normalized center + intensity 0..1 + radius)
  heatBlobs: { x: number; y: number; intensity: number; radius: number }[]
  trend: ProbabilityPoint[]
  recentCommands: OperatorCommand[]
  telemetry: { altM: number; spdMs: number; hdgDeg: number; feedTime: string }
  // --- guide-home overlay (additive; null/'searching' during the search phase) ---
  // The walkable route the drone leads the subject along, back to the operators.
  guidancePath?: { x: number; y: number }[] | null
  // The moving subject (follower) and the operators/home (where the drone leads them).
  subjectPos?: { x: number; y: number } | null
  operatorPos?: { x: number; y: number } | null
  guidanceStatus?: 'searching' | 'guiding' | 'arrived'
}
