import { ArrowUp, ArrowDown, Flame } from 'lucide-react'
import type { MissionStats, ProbabilityPoint } from '../types'

interface Props {
  stats: MissionStats // detections + area covered, live from /state
  trend: ProbabilityPoint[] // top-5% belief concentration over time (for the latest value + delta)
  lastUpdate: string
}

export default function MapUpdateSummary({ stats, trend, lastUpdate }: Props) {
  // Latest belief concentration and its change vs. the previous point, so the "high probability
  // area" row reflects the real map instead of a hardcoded number.
  const mass = trend.length ? trend[trend.length - 1].mass : 0
  const prevMass = trend.length > 1 ? trend[trend.length - 2].mass : mass
  const delta = mass - prevMass
  const deltaStr =
    delta > 0.5 ? ` (↑ ${delta.toFixed(0)}%)` : delta < -0.5 ? ` (↓ ${Math.abs(delta).toFixed(0)}%)` : ''

  const rows = [
    {
      icon: ArrowUp,
      color: 'text-accent-green',
      ring: 'bg-accent-green/15',
      title: 'Detection evidence added',
      sub: `${stats.detections} detection${stats.detections === 1 ? '' : 's'} (capped & fused)`,
    },
    {
      icon: ArrowDown,
      color: 'text-accent-blue',
      ring: 'bg-accent-blue/15',
      title: 'Searched areas (no detection)',
      sub: `${stats.areaCoveredKm2.toFixed(2)} km² covered`,
    },
    {
      icon: Flame,
      color: 'text-accent-red',
      ring: 'bg-accent-red/15',
      title: 'High probability area',
      sub: `${mass.toFixed(0)}% of belief${deltaStr}`,
    },
  ]

  return (
    <div className="panel flex flex-col p-3">
      <div className="panel-header">Map Update Summary</div>

      <div className="mt-2 flex-1 space-y-2.5">
        {rows.map(({ icon: Icon, color, ring, title, sub }) => (
          <div key={title} className="flex items-center gap-3">
            <div className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${ring}`}>
              <Icon className={`h-4 w-4 ${color}`} />
            </div>
            <div className="leading-tight">
              <div className="text-[13px] font-medium text-white">{title}</div>
              <div className="text-[11px] text-slate-500">{sub}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex items-center border-t border-white/5 pt-2">
        <span className="text-[11px] text-slate-500">Last Update: {lastUpdate}</span>
      </div>
    </div>
  )
}
