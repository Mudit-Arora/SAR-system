import { useEffect, useRef } from 'react'
import { Phone, PhoneOff } from 'lucide-react'
import { useTranscript, type TranscriptTurn } from '../hooks/useTranscript'

// WebSocket feed of the deployed voice agent. Override per-environment with
// VITE_AGENT_WS_URL in dashboard/.env (e.g. ws://localhost:8080/transcript for local).
const AGENT_WS_URL =
  import.meta.env.VITE_AGENT_WS_URL ?? 'wss://golden-seastar-977.fly.dev/transcript'

export default function LiveTranscript() {
  const { turns, status, callActive } = useTranscript(AGENT_WS_URL)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns])

  return (
    <div className="panel flex flex-col p-3">
      <div className="flex items-center justify-between">
        <div className="panel-header">Live Call Transcript</div>
        <div className="flex items-center gap-1.5 text-[11px]">
          {callActive ? (
            <span className="flex items-center gap-1 font-medium text-accent-green">
              <Phone className="h-3.5 w-3.5" /> Call active
            </span>
          ) : (
            <span className="flex items-center gap-1 text-slate-500">
              <PhoneOff className="h-3.5 w-3.5" />
              {status === 'open'
                ? 'Waiting for call'
                : status === 'connecting'
                  ? 'Connecting…'
                  : 'Disconnected'}
            </span>
          )}
        </div>
      </div>

      <div className="mt-2 max-h-64 min-h-[8rem] flex-1 space-y-2 overflow-y-auto rounded-lg bg-base-900/60 p-3">
        {turns.length === 0 ? (
          <div className="grid h-full place-items-center text-center text-[12px] text-slate-500">
            No transcript yet. Waiting for a caller…
          </div>
        ) : (
          turns.map((t, i) => <TurnBubble key={i} turn={t} />)
        )}
        <div ref={endRef} />
      </div>
    </div>
  )
}

function TurnBubble({ turn }: { turn: TranscriptTurn }) {
  const isAgent = turn.role === 'assistant'
  return (
    <div className={`flex ${isAgent ? 'justify-start' : 'justify-end'}`}>
      <div
        className={`max-w-[80%] rounded-lg px-2.5 py-1.5 text-[12px] leading-snug ${
          isAgent
            ? 'bg-accent-blue/15 text-slate-100 ring-1 ring-accent-blue/20'
            : 'bg-base-700/70 text-slate-200'
        }`}
      >
        <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
          {isAgent ? 'SAR Operator' : 'Caller'}
        </div>
        {turn.content}
      </div>
    </div>
  )
}
