import { useEffect, useState } from 'react'

// One conversation turn pushed from the voice agent's /transcript feed.
export interface TranscriptTurn {
  role: string // "assistant" (SAR operator) | "user" (caller)
  content: string
  ts: string
}

export type ConnStatus = 'connecting' | 'open' | 'closed'

// Subscribe to the voice agent's live transcript WebSocket.
// Accumulates turns for the current call and auto-reconnects on drop.
export function useTranscript(url: string) {
  const [turns, setTurns] = useState<TranscriptTurn[]>([])
  const [status, setStatus] = useState<ConnStatus>('connecting')
  const [callActive, setCallActive] = useState(false)

  useEffect(() => {
    let stopped = false
    let retry: ReturnType<typeof setTimeout>
    let ws: WebSocket

    const connect = () => {
      setStatus('connecting')
      ws = new WebSocket(url)

      ws.onopen = () => setStatus('open')

      ws.onmessage = (e) => {
        let msg: Record<string, unknown>
        try {
          msg = JSON.parse(e.data)
        } catch {
          return
        }
        if (msg.type === 'turn') {
          setTurns((t) => [
            ...t,
            { role: String(msg.role), content: String(msg.content), ts: String(msg.ts) },
          ])
        } else if (msg.type === 'call_started') {
          setCallActive(true)
          setTurns([]) // fresh transcript per call
        } else if (msg.type === 'call_ended') {
          setCallActive(false)
        }
      }

      ws.onclose = () => {
        setStatus('closed')
        setCallActive(false)
        if (!stopped) retry = setTimeout(connect, 2000)
      }

      ws.onerror = () => ws.close()
    }

    connect()

    return () => {
      stopped = true
      clearTimeout(retry)
      ws?.close()
    }
  }, [url])

  return { turns, status, callActive }
}
