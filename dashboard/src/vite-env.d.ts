/// <reference types="vite/client" />

interface ImportMetaEnv {
  // WebSocket URL of the voice agent's /transcript feed.
  readonly VITE_AGENT_WS_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
