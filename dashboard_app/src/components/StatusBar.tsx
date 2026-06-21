import { CheckCircle2, Satellite, Wifi, HardDrive } from 'lucide-react'

export default function StatusBar() {
  return (
    <footer className="flex h-9 items-center justify-between border-t border-white/5 bg-base-900/90 px-4 text-[11px] text-slate-400">
      <div className="flex items-center gap-4">
        <span>
          <span className="text-slate-500">Data:</span> Simulated
        </span>
        <span className="hidden sm:inline">
          <span className="text-slate-500">Region:</span> Pine Ridge, CA
        </span>
        <span className="hidden sm:inline">
          <span className="text-slate-500">Weather:</span> 12°C, Clear
        </span>
        <span className="hidden md:inline">
          <span className="text-slate-500">Wind:</span> 8 km/h NW
        </span>
      </div>
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-1.5 text-accent-green">
          <CheckCircle2 className="h-3.5 w-3.5" /> All Systems Go
        </span>
        <span className="flex items-center gap-1.5">
          <Satellite className="h-3.5 w-3.5 text-slate-500" /> GPS
          <Bars />
        </span>
        <span className="flex items-center gap-1.5">
          <Wifi className="h-3.5 w-3.5 text-slate-500" /> Link
          <Bars />
        </span>
        <span className="flex items-center gap-1.5">
          <HardDrive className="h-3.5 w-3.5 text-slate-500" /> Storage
          <StorageBar />
          78%
        </span>
      </div>
    </footer>
  )
}

function Bars() {
  return (
    <span className="flex items-end gap-0.5">
      {[3, 5, 7, 9].map((h, i) => (
        <span
          key={i}
          className={`w-0.5 rounded-sm ${i < 3 ? 'bg-accent-green' : 'bg-slate-600'}`}
          style={{ height: h }}
        />
      ))}
    </span>
  )
}

function StorageBar() {
  return (
    <span className="flex gap-0.5">
      {Array.from({ length: 5 }).map((_, i) => (
        <span
          key={i}
          className={`h-2 w-1.5 rounded-sm ${i < 4 ? 'bg-accent-green' : 'bg-slate-600'}`}
        />
      ))}
    </span>
  )
}
