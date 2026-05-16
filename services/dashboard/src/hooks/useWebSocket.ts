import { useEffect, useRef, useCallback, useState } from 'react'
import type { WSEvent } from '../types'

type Handler = (event: WSEvent) => void

interface Options {
  /** Which run_id or session_id channel to subscribe to */
  channel?: string
  onEvent?: Handler
  enabled?: boolean
}

export function useWebSocket({ channel, onEvent, enabled = true }: Options = {}) {
  const ws = useRef<WebSocket | null>(null)
  const retries = useRef(0)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    if (!enabled) return
    const url = channel
      ? `/ws?channel=${encodeURIComponent(channel)}`
      : '/ws'
    // In Vite dev the proxy handles ws:// → ws://orchestrator:8000
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const sock = new WebSocket(`${proto}://${window.location.host}${url}`)
    ws.current = sock

    sock.onopen = () => {
      setConnected(true)
      retries.current = 0
    }

    sock.onmessage = (ev) => {
      try {
        const raw = JSON.parse(ev.data)
        const data: WSEvent = { payload: {}, ...raw }
        onEventRef.current?.(data)
      } catch {
        // non-JSON heartbeat — ignore
      }
    }

    sock.onclose = () => {
      setConnected(false)
      const delay = Math.min(1000 * 2 ** retries.current, 30_000)
      retries.current++
      setTimeout(connect, delay)
    }

    sock.onerror = () => sock.close()
  }, [channel, enabled])

  useEffect(() => {
    connect()
    return () => {
      ws.current?.close()
    }
  }, [connect])

  const send = useCallback((data: unknown) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(data))
    }
  }, [])

  return { connected, send }
}
