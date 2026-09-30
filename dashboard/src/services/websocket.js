/**
 * Real-time WebSocket connection to /ws/counselor
 * Handles auto-reconnect and routes typed events to named callbacks.
 */

const WS_BASE = 'ws://localhost:8000';

/**
 * Creates and manages the counselor WebSocket connection.
 *
 * @param {string} token  - JWT bearer token
 * @param {object} callbacks
 *   - onStatusChange(status: 'connecting' | 'connected' | 'disconnected')
 *   - onEscalation(data) – called when a new escalation event arrives
 *   - onMessage(data)    – called when a new chat message event arrives
 * @returns {{ close() }}
 */
export function createWebSocketClient(token, { onStatusChange, onEscalation, onMessage } = {}) {
  let ws = null;
  let reconnectTimeout = null;
  let isClosedManually = false;

  const connect = () => {
    if (isClosedManually || !token) return;

    onStatusChange?.('connecting');
    ws = new WebSocket(`${WS_BASE}/ws/counselor?token=${token}`);

    ws.onopen = () => {
      onStatusChange?.('connected');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Route by event type (backend should set data.type)
        if (data.type === 'escalation' || data.type === 'new_escalation') {
          onEscalation?.(data);
        } else if (data.type === 'message' || data.type === 'new_message') {
          onMessage?.(data);
        } else {
          // Fallback: if no type, treat as escalation refresh trigger
          onEscalation?.(data);
        }
      } catch {
        // Heartbeat or non-JSON ping — ignore
      }
    };

    ws.onclose = () => {
      onStatusChange?.('disconnected');
      if (!isClosedManually) {
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };

    ws.onerror = () => {
      ws?.close();
    };
  };

  connect();

  return {
    close() {
      isClosedManually = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      ws?.close();
    },
  };
}

// Legacy alias for backward compatibility
export const createCounselorSocket = createWebSocketClient;
