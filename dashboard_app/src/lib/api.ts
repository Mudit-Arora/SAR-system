// =============================================================================
// api.ts
// -----------------------------------------------------------------------------
// Responsible for: The single base URL for the brain's integration server.
// Role in project: Shared by useMapState (polls /state) and ProbabilityMap (loads
//                  /terrain.png), so the backend location is configured in ONE place.
// =============================================================================

// Where the integration server lives. Defaults to the local uvicorn (port 8000); override
// with VITE_API_BASE in the environment for a deployed backend.
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
