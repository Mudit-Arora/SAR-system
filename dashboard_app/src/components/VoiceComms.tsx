import { useEffect, useRef, useState } from 'react'
import { Mic, Volume2 } from 'lucide-react'
import type { MapState, OperatorCommand } from '../types'
import { API_BASE } from '../lib/api'

// Friendly display names + a BCP-47 tag (for the browser-TTS fallback voice) per language code.
const LANG_INFO: Record<string, { name: string; bcp47: string }> = {
  en: { name: 'English', bcp47: 'en-US' },
  es: { name: 'Español', bcp47: 'es-ES' },
}

const DEFAULT_MESSAGE = 'Stay where you are. Help is coming. We can see you.'

interface Props {
  commands: OperatorCommand[]
  broadcast?: MapState['subjectBroadcast']
}

export default function VoiceComms({ commands, broadcast }: Props) {
  const [tab, setTab] = useState<'operator' | 'subject'>('operator')
  const [lang] = useState('en')
  // Remember which broadcast we've already auto-spoken (keyed by its timestamp), so it fires once.
  const autoSpokenRef = useRef<string | null>(null)

  const audioLangs = broadcast?.audioLangs ?? []
  const message = broadcast?.texts?.[lang] ?? broadcast?.texts?.en ?? DEFAULT_MESSAGE

  // Speak the current message: Deepgram audio if available for this language, else browser TTS.
  function speak() {
    const text = broadcast?.texts?.[lang] ?? DEFAULT_MESSAGE
    if (broadcast && audioLangs.includes(lang)) {
      const audio = new Audio(`${API_BASE}/broadcast.mp3?lang=${lang}`)
      // If the Deepgram audio can't play (offline / blocked), fall back to the browser voice.
      audio.play().catch(() => browserSpeak(text, lang))
    } else {
      browserSpeak(text, lang)
    }
  }

  function browserSpeak(text: string, code: string) {
    if (!('speechSynthesis' in window)) return
    const utter = new SpeechSynthesisUtterance(text)
    utter.lang = LANG_INFO[code]?.bcp47 ?? 'en-US'
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(utter)
  }

  // Best-effort: speak the broadcast once when it first appears (the located moment). Browser
  // autoplay policy may block this until a user gesture, so the "Speak Message" button is the
  // reliable trigger; this is just the dramatic auto-announce when allowed.
  useEffect(() => {
    if (broadcast && broadcast.timestamp !== autoSpokenRef.current) {
      autoSpokenRef.current = broadcast.timestamp
      setTab('subject')
      speak()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [broadcast?.timestamp])

  const isDeepgram = broadcast != null && audioLangs.includes(lang)

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
            {commands.length === 0 && (
              <div className="rounded-md bg-base-900/40 px-2.5 py-1.5 text-[11px] text-slate-500">
                No operator commands yet.
              </div>
            )}
          </div>
        </div>

        {/* System message to subject */}
        <div>
          <div className="mb-1.5 flex items-center justify-between text-[11px] font-semibold text-slate-400">
            <span>System Message to Subject</span>
            {broadcast && (
              <span className="rounded bg-accent-green/15 px-1.5 py-0.5 text-[9px] font-bold text-accent-green">
                LOCATED
              </span>
            )}
          </div>
          <div className="rounded-lg bg-accent-green/10 p-2.5 ring-1 ring-accent-green/20">
            <div className="flex items-start gap-2">
              <Volume2 className="mt-0.5 h-4 w-4 shrink-0 text-accent-green" />
              <p className="text-[12px] leading-snug text-slate-200">
                {message}
                <span className="mt-0.5 block text-[10px] text-slate-500">
                  ({LANG_INFO[lang]?.name ?? lang}
                  {isDeepgram ? ' · Deepgram voice' : ' · browser voice'})
                </span>
              </p>
            </div>
          </div>
          <div className="mt-2 flex gap-2">
            <button
              onClick={speak}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-accent-blue py-1.5 text-[12px] font-semibold text-white hover:bg-blue-500"
            >
              <Volume2 className="h-3.5 w-3.5" /> Speak Message
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
