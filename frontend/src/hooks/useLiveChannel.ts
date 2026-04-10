import { useEffect, useState } from 'react'

type ConnectionState = 'connecting' | 'open' | 'closed' | 'error'

function toWebSocketUrl(path: string) {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${path}`
}

export function useLiveChannel<T>(path: string) {
  const [data, setData] = useState<T | null>(null)
  const [state, setState] = useState<ConnectionState>('connecting')

  useEffect(() => {
    let active = true
    let socket: WebSocket | null = null
    let retryTimer: number | null = null

    const connect = () => {
      setState('connecting')
      socket = new WebSocket(toWebSocketUrl(path))

      socket.onopen = () => {
        if (active) {
          setState('open')
        }
      }

      socket.onmessage = (event) => {
        if (!active) {
          return
        }
        try {
          setData(JSON.parse(event.data) as T)
        } catch {
          setState('error')
        }
      }

      socket.onerror = () => {
        if (active) {
          setState('error')
        }
      }

      socket.onclose = () => {
        if (!active) {
          return
        }
        setState('closed')
        retryTimer = window.setTimeout(connect, 2500)
      }
    }

    connect()

    return () => {
      active = false
      if (retryTimer !== null) {
        window.clearTimeout(retryTimer)
      }
      socket?.close()
    }
  }, [path])

  return { data, state }
}
