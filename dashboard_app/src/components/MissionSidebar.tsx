import {
  Clock,
  Compass,
  Plane,
  ScanSearch,
  UserRound,
  Mountain,
} from 'lucide-react'
import type { MissionStats } from '../types'
import { HEAT_GRADIENT_CSS } from '../lib/colors'

interface Props {
  missionName: string
  startedAt: string
  stats: MissionStats
}

export default function MissionSidebar({
  missionName,
  startedAt,
  stats,
}: Props) {
  const statRows = [
    { icon: Clock, label: 'Search Time', value: stats.searchTime, mono: true },
    { icon: Compass, label: 'Area Covered', value: `${stats.areaCoveredKm2.toFixed(2)} km²` },
    { icon: Plane, label: 'Flight Distance', value: `${stats.flightDistanceKm.toFixed(1)} km` },
    { icon: ScanSearch, label: 'Detections', value: String(stats.detections) },
    { icon: UserRound, label: 'Persons Found', value: String(stats.personsFound), good: true },
  ]

  return (
    <aside className="flex w-[244px] shrink-0 flex-col gap-3 overflow-y-auto border-r border-white/5 bg-base-900/60 p-3">
      {/* Mission card */}
      <div className="panel p-3">
        <div className="panel-header flex items-center gap-1.5">
          <Mountain className="h-3 w-3 text-accent-cyan" /> Mission
        </div>
        <div className="mt-1 text-base font-bold leading-tight text-white">{missionName}</div>
        <div className="mt-1 text-[11px] text-slate-500">Started {startedAt}</div>
      </div>

      {/* Stats */}
      <div className="panel divide-y divide-white/5">
        {statRows.map(({ icon: Icon, label, value, mono, good }) => (
          <div key={label} className="flex items-center gap-3 px-3 py-2.5">
            <div className="grid h-8 w-8 place-items-center rounded-lg bg-base-700/60">
              <Icon className="h-4 w-4 text-accent-cyan" />
            </div>
            <div className="min-w-0">
              <div className="text-[11px] text-slate-400">{label}</div>
              <div
                className={`text-sm font-semibold ${good ? 'text-accent-green' : 'text-white'} ${
                  mono ? 'font-mono tracking-tight' : ''
                }`}
              >
                {value}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Probability legend */}
      <div className="panel p-3">
        <div className="panel-header">Probability</div>
        <div
          className="mt-2 h-2.5 w-full rounded-full"
          style={{ background: HEAT_GRADIENT_CSS }}
        />
        <div className="mt-1.5 flex justify-between text-[10px] text-slate-500">
          <span>Very Low</span>
          <span>Very High</span>
        </div>
      </div>
    </aside>
  )
}
