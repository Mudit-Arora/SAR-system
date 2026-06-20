import { useState } from 'react'
import { Mic, Volume2, ChevronDown } from 'lucide-react'
import type { OperatorCommand } from '../types'

export default function VoiceComms({ commands }: { commands: OperatorCommand[] }) {
  const [tab, setTab] = useState<'operator' | 'subject'>('operator')

  return (
    <div className="panel flex flex-col p-3">
      <div className="flex items-center justify-between">
        <div className="panel-header">Voice & Comms</div>
        <div className="flex rounded-md bg-base-900/80 p-0.5 text-[11px]">
          {(['operator', 'subject'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-2 py-0.5 font-medium capitalize transition ${
                tab === t ? 'bg-accent-blue text-white' : 'text-slate-400'
              }`}
            >
              {t === 'operator' ? 'Operator' : 'To Subject'}
            </button>
          ))}
        </div>
      </div>

      {/* Listening state */}
      <div className="mt-2 flex items-center gap-2 rounded-lg bg-base-900/60 px-3 py-2">
        <div className="grid h-7 w-7 place-items-center rounded-full bg-accent-cyan/15">
          <Mic className="h-3.5 w-3.5 text-accent-cyan" />
        </div>
        <div className="leading-tight">
          <div className="flex items-center gap-1 text-[12px] font-medium text-accent-cyan">
            Listening
            <span className="flex gap-0.5">
              {[0, 1, 2].map((i) => (
                <span
                  key={i}
                  className="h-1 w-1 rounded-full bg-accent-cyan animate-blink"
                  style={{ animationDelay: `${i * 0.2}s` }}
                />
              ))}
            </span>
          </div>
          <div className="text-[11px] text-slate-500">Try "Where should we look next?"</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
        {/* Recent commands */}
        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-slate-400">Recent Commands</div>
          <div className="space-y-1.5">
            {commands.map((c, i) => (
              <div
                key={i}
                className="flex items-center justify-between rounded-md bg-base-900/50 px-2.5 py-1.5 text-[12px] text-slate-300"
              >
                <span className="truncate">{c.text}</span>
                <span className="ml-2 shrink-0 font-mono text-[10px] text-slate-500">{c.time}</span>
              </div>
            ))}
          </div>
        </div>

        {/* System message to subject */}
        <div>
          <div className="mb-1.5 text-[11px] font-semibold text-slate-400">System Message to Subject</div>
          <div className="rounded-lg bg-accent-green/10 p-2.5 ring-1 ring-accent-green/20">
            <div className="flex items-start gap-2">
              <Volume2 className="mt-0.5 h-4 w-4 shrink-0 text-accent-green" />
              <p className="text-[12px] leading-snug text-slate-200">
                Stay where you are. Help is coming. We can see you.
                <span className="mt-0.5 block text-[10px] text-slate-500">(English)</span>
              </p>
            </div>
          </div>
          <div className="mt-2 flex gap-2">
            <button className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-accent-blue py-1.5 text-[12px] font-semibold text-white hover:bg-blue-500">
              <Volume2 className="h-3.5 w-3.5" /> Speak Message
            </button>
            <button className="flex items-center gap-1 rounded-md bg-base-700/70 px-2.5 py-1.5 text-[12px] text-slate-200 hover:bg-base-600">
              English <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
