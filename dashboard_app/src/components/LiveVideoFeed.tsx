import { Video } from 'lucide-react'
import type { MapState } from '../types'

export default function LiveVideoFeed({ telemetry }: { telemetry: MapState['telemetry'] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between px-3 py-2">
        <div className="panel-header flex items-center gap-1.5">
          <Video className="h-3 w-3 text-accent-cyan" /> Live Video Feed
        </div>
        <span className="flex items-center gap-1 rounded bg-accent-red/15 px-1.5 py-0.5 text-[10px] font-bold text-accent-red">
          <span className="h-1.5 w-1.5 rounded-full bg-accent-red animate-blink" /> LIVE
        </span>
      </div>

      {/* Feed frame (procedural forest canopy stand-in for drone footage) */}
      <div className="relative aspect-video w-full overflow-hidden">
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              'radial-gradient(80% 60% at 60% 30%, #2c4a2b 0%, #1c3320 45%, #0f1f13 100%),' +
              'repeating-linear-gradient(35deg, rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 2px, transparent 2px, transparent 7px),' +
              'repeating-linear-gradient(-50deg, rgba(255,255,255,0.04) 0px, rgba(255,255,255,0.04) 1px, transparent 1px, transparent 6px)',
          }}
        />
        {/* Detection bounding box on the subject */}
        <div className="absolute left-[46%] top-[34%] h-[34%] w-[16%]">
          <div className="h-full w-full rounded-sm border-2 border-accent-green shadow-[0_0_12px_rgba(34,197,94,0.6)]" />
          <span className="absolute -top-5 left-0 rounded bg-accent-green px-1 py-0.5 text-[9px] font-bold text-base-950">
            PERSON 0.92
          </span>
          {/* subject silhouette hint */}
          <div className="absolute bottom-1 left-1/2 h-3 w-1.5 -translate-x-1/2 rounded-full bg-slate-900/70" />
        </div>

        {/* HUD overlay */}
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-gradient-to-t from-black/70 to-transparent px-3 py-1.5 font-mono text-[10px] text-slate-200">
          <span>ALT {telemetry.altM} m</span>
          <span>SPD {telemetry.spdMs.toFixed(1)} m/s</span>
          <span>HDG {telemetry.hdgDeg}°</span>
          <span>{telemetry.feedTime}</span>
        </div>
      </div>
    </div>
  )
}
