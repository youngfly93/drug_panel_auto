import { ref, onUnmounted } from 'vue'

export interface ProgressMessage {
  type: 'progress' | 'completed' | 'failed'
  task_id: string
  data?: {
    current: number
    total: number
    percent: number
    message: string
  }
}

/**
 * WebSocket composable for real-time batch task progress.
 */
export function useWebSocket(taskId: string) {
  const messages = ref<ProgressMessage[]>([])
  const connected = ref(false)
  const lastMessage = ref<ProgressMessage | null>(null)
  let ws: WebSocket | null = null

  function connect() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    ws = new WebSocket(`${protocol}//${host}/ws/tasks/${taskId}/progress`)

    ws.onopen = () => {
      connected.value = true
    }

    ws.onmessage = (event) => {
      try {
        const msg: ProgressMessage = JSON.parse(event.data)
        messages.value.push(msg)
        lastMessage.value = msg
      } catch {
        // ignore non-JSON messages
      }
    }

    ws.onclose = () => {
      connected.value = false
    }

    ws.onerror = () => {
      connected.value = false
    }
  }

  function disconnect() {
    if (ws) {
      ws.close()
      ws = null
    }
  }

  function send(data: string) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(data)
    }
  }

  onUnmounted(disconnect)

  return { messages, connected, lastMessage, connect, disconnect, send }
}
