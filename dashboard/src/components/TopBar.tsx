import { LayoutDashboard, Map, Crosshair, Database, Settings, Mic, Radio } from 'lucide-react'
import { useState } from 'react'

const NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'map', label: 'Map', icon: Map },
  { id: 'missions', label: 'Missions', icon: Crosshair },
  { id: 'data', label: 'Data', icon: Database },
  { id: 'settings', label: 'Settings', icon: Settings },
]

export default function TopBar() {
  const [active, setActive] = useState('dashboard')

  return (
    <header className="flex h-14 items-center justify-between border-b border-white/5 bg-base-900/90 px-4">
      {/* Brand */}
      <div className="flex items-center gap-3">
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-accent-cyan/10 ring-1 ring-accent-cyan/30">
          <Crosshair className="h-5 w-5 text-accent-cyan" />
        </div>
        <div className="leading-tight">
          <div className="text-sm font-bold tracking-wide text-white">SAR SUPPORT SYSTEM</div>
          <div className="text-[10px] text-slate-400">Search & Rescue Decision Layer</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="hidden items-center gap-1 md:flex">
        {NAV.map(({ id, label, icon: Icon }) => {
          const on = id === active
          return (
            <button
              key={id}
              onClick={() => setActive(id)}
              className={`relative flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition ${
                on ? 'text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon className="h-4 w-4" />
              {label}
              {on && (
                <span className="absolute -bottom-[10px] left-2 right-2 h-0.5 rounded-full bg-accent-cyan" />
              )}
            </button>
          )
        })}
      </nav>

      {/* Right cluster */}
      <div className="flex items-center gap-3">
        <div className="hidden text-right leading-tight lg:block">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">System Status</div>
          <div className="text-xs font-semibold text-accent-green">OPERATIONAL</div>
        </div>
        <button className="grid h-9 w-9 place-items-center rounded-full bg-base-700 text-slate-300 hover:bg-base-600">
          <Mic className="h-4 w-4" />
        </button>
        <button className="flex items-center gap-2 rounded-full bg-accent-blue px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-accent-blue/30 hover:bg-blue-500">
          <Radio className="h-4 w-4" />
          Push to Talk
        </button>
        <div className="grid h-9 w-9 place-items-center rounded-full bg-gradient-to-br from-accent-cyan to-accent-blue text-xs font-bold text-base-950">
          OP
        </div>
      </div>
    </header>
  )
}
