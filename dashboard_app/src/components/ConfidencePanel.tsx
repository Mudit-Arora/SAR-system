interface Props {
  confidence: number
  threshold: number
}

export default function ConfidencePanel({ confidence, threshold }: Props) {
  const declared = confidence >= threshold
  return (
    <div className="panel flex w-[220px] shrink-0 flex-col justify-center px-4 py-2.5">
      <div className="panel-header">Confidence to Declare</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className={`text-3xl font-bold ${declared ? 'text-accent-green' : 'text-accent-amber'}`}>
          {confidence}%
        </span>
        <span className="text-[11px] text-slate-500">Threshold: {threshold}%</span>
      </div>
      <div className="relative mt-2 h-1.5 w-full rounded-full bg-base-700">
        <div
          className="h-full rounded-full bg-gradient-to-r from-accent-amber to-accent-green transition-all"
          style={{ width: `${confidence}%` }}
        />
        <div
          className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 rounded bg-white/80"
          style={{ left: `${threshold}%` }}
          title={`Threshold ${threshold}%`}
        />
      </div>
    </div>
  )
}
