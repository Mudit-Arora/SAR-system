import { Check } from 'lucide-react'
import type { LoopStep } from '../types'

export default function SearchLoop({ steps }: { steps: LoopStep[] }) {
  return (
    <div className="panel px-4 py-2.5">
      <div className="panel-header mb-2">Search Loop</div>
      <div className="flex items-center">
        {steps.map((s, i) => (
          <div key={s.id} className="flex flex-1 items-center">
            <Step step={s} />
            {i < steps.length - 1 && (
              <div
                className={`mx-1 h-px flex-1 ${
                  s.status === 'done' ? 'bg-accent-cyan/50' : 'bg-base-600'
                }`}
              />
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function Step({ step }: { step: LoopStep }) {
  const { status, id, label } = step
  const ring =
    status === 'done'
      ? 'bg-accent-cyan text-base-950'
      : status === 'live'
        ? 'bg-accent-blue text-white ring-4 ring-accent-blue/25'
        : 'bg-base-700 text-slate-400'

  return (
    <div className="flex min-w-0 items-center gap-2">
      <div className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[11px] font-bold ${ring}`}>
        {status === 'done' ? <Check className="h-3.5 w-3.5" /> : id}
      </div>
      <div className="min-w-0 leading-tight">
        <div
          className={`truncate text-[13px] font-medium ${
            status === 'next' ? 'text-slate-400' : 'text-white'
          }`}
        >
          {label}
        </div>
        <div
          className={`text-[10px] capitalize ${
            status === 'live'
              ? 'text-accent-blue'
              : status === 'done'
                ? 'text-accent-cyan/70'
                : 'text-slate-500'
          }`}
        >
          {status === 'live' ? 'Live' : status === 'done' ? 'Done' : 'Next'}
        </div>
      </div>
    </div>
  )
}
