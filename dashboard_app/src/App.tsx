import TopBar from './components/TopBar'
import StatusBar from './components/StatusBar'
import MissionSidebar from './components/MissionSidebar'
import SearchLoop from './components/SearchLoop'
import ConfidencePanel from './components/ConfidencePanel'
import ProbabilityMap from './components/ProbabilityMap'
import LiveVideoFeed from './components/LiveVideoFeed'
import DetectionsList from './components/DetectionsList'
import ProbabilityTrend from './components/ProbabilityTrend'
import MapUpdateSummary from './components/MapUpdateSummary'
import LiveTranscript from './components/LiveTranscript'
import { useMapState } from './hooks/useMapState'

export default function App() {
  // Live MapState from the brain's integration server (falls back to mockState when offline).
  const { state } = useMapState()

  return (
    <div className="flex h-screen flex-col bg-base-950 text-slate-200">
      <TopBar />

      <div className="flex min-h-0 flex-1">
        <MissionSidebar
          missionName={state.missionName}
          startedAt={state.startedAt}
          stats={state.stats}
        />

        {/* Main work area */}
        <main className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
          {/* Top strip: loop + confidence + live feed header sit across the row */}
          <div className="flex gap-3">
            <div className="min-w-0 flex-1">
              <SearchLoop steps={state.loop} />
            </div>
            <ConfidencePanel
              confidence={state.confidenceToDeclare}
              threshold={state.declareThreshold}
            />
          </div>

          {/* Middle: map (center) + right rail */}
          <div className="flex min-h-[440px] flex-1 gap-3">
            <div className="flex min-w-0 flex-1 flex-col">
              {/* DEMO MODE: the map shows a pre-rendered 3-drone search + guide-home gif instead
                  of the live server-rendered map. */}
              <ProbabilityMap />
            </div>

            {/* Right rail widened (the map is a centered square now, so it freed up horizontal
                space) — this enlarges the Live Video Feed without shrinking the map's square. */}
            <div className="flex w-[420px] shrink-0 flex-col gap-3">
              <LiveVideoFeed telemetry={state.telemetry} />
              <DetectionsList detections={state.detections} />
            </div>
          </div>

          {/* Bottom row */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <ProbabilityTrend data={state.trend} now={state.confidenceToDeclare} />
            <MapUpdateSummary stats={state.stats} trend={state.trend} lastUpdate={state.telemetry.feedTime} />
            {/* Live transcript from the deployed voice agent (real data) */}
            <LiveTranscript />
          </div>
        </main>
      </div>

      <StatusBar />
    </div>
  )
}
