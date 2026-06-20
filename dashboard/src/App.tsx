import { useMemo, useState } from 'react'
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
import VoiceComms from './components/VoiceComms'
import { mockState } from './data/mockState'

export default function App() {
  // Local copy so layer toggles are interactive (dashboard reads state; toggles are view-only).
  const [layers, setLayers] = useState(mockState.layers)

  const toggleLayer = (id: string) =>
    setLayers((ls) => ls.map((l) => (l.id === id ? { ...l, enabled: !l.enabled } : l)))

  const layerOn = useMemo(
    () => Object.fromEntries(layers.map((l) => [l.id, l.enabled])),
    [layers],
  )

  return (
    <div className="flex h-screen flex-col bg-base-950 text-slate-200">
      <TopBar />

      <div className="flex min-h-0 flex-1">
        <MissionSidebar
          missionName={mockState.missionName}
          startedAt={mockState.startedAt}
          stats={mockState.stats}
          layers={layers}
          onToggleLayer={toggleLayer}
        />

        {/* Main work area */}
        <main className="flex min-w-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
          {/* Top strip: loop + confidence + live feed header sit across the row */}
          <div className="flex gap-3">
            <div className="min-w-0 flex-1">
              <SearchLoop steps={mockState.loop} />
            </div>
            <ConfidencePanel
              confidence={mockState.confidenceToDeclare}
              threshold={mockState.declareThreshold}
            />
          </div>

          {/* Middle: map (center) + right rail */}
          <div className="flex min-h-[440px] flex-1 gap-3">
            <div className="flex min-w-0 flex-1 flex-col">
              <ProbabilityMap
                state={mockState}
                showHeat={layerOn['prob']}
                showPath={layerOn['path']}
                showDetections={layerOn['detections']}
                showSearched={layerOn['searched']}
              />
            </div>

            <div className="flex w-[320px] shrink-0 flex-col gap-3">
              <LiveVideoFeed telemetry={mockState.telemetry} />
              <DetectionsList detections={mockState.detections} />
            </div>
          </div>

          {/* Bottom row */}
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
            <ProbabilityTrend data={mockState.trend} now={mockState.confidenceToDeclare} />
            <MapUpdateSummary lastUpdate={mockState.telemetry.feedTime} />
            <VoiceComms commands={mockState.recentCommands} />
          </div>
        </main>
      </div>

      <StatusBar />
    </div>
  )
}
