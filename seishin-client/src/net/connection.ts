import { updateState, appState } from '../state.ts';
import { SeiMessage, ConnectionStatus } from '../types.ts';
import { connectToSei, setHandlers, disconnect } from './websocket.ts';

const BASE_DELAY = 500;
const MAX_DELAY = 30000;
const MAX_RETRIES = 10;
const HEARTBEAT_INTERVAL = 15000;
const HEARTBEAT_MISS_THRESHOLD = 2;

export class ConnectionManager {
  private url = '';
  private isDeliberateClose = false;
  private retryCount = 0;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private missedHeartbeats = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  // External handlers for message/binary data (wired by later plans)
  public onSeiMessage: ((msg: SeiMessage) => void) | null = null;
  public onSeiBinary: ((data: Uint8Array) => void) | null = null;

  async connect(url: string): Promise<void> {
    this.url = url;
    this.isDeliberateClose = false;
    this.retryCount = 0;
    this.clearTimers();

    setStatus('connecting');

    try {
      setHandlers({
        onMessage: (msg) => this.handleMessage(msg),
        onBinary: (data) => this.handleBinary(data),
        onClose: () => this.handleClose(),
      });

      await connectToSei(url);

      setStatus('connected');
      updateState({ serverUrl: url });
      this.startHeartbeat();
    } catch (err) {
      setStatus('disconnected');
      throw err;
    }
  }

  async disconnect(): Promise<void> {
    this.isDeliberateClose = true;
    this.clearTimers();
    await disconnect();
    // Clear messages on deliberate close per D-07/CLIENT-06
    updateState({ messages: [] });
    setStatus('disconnected');
  }

  private handleMessage(msg: SeiMessage): void {
    // Reset heartbeat miss counter on any server message
    this.missedHeartbeats = 0;
    if (appState.connection === 'degraded') {
      setStatus('connected');
    }
    this.onSeiMessage?.(msg);
  }

  private handleBinary(data: Uint8Array): void {
    // Binary data also confirms connectivity
    this.missedHeartbeats = 0;
    if (appState.connection === 'degraded') {
      setStatus('connected');
    }
    this.onSeiBinary?.(data);
  }

  private handleClose(): void {
    this.clearTimers();

    if (this.isDeliberateClose) {
      setStatus('disconnected');
      return;
    }

    // Unexpected close -- attempt reconnect
    this.attemptReconnect();
  }

  private startHeartbeat(): void {
    this.missedHeartbeats = 0;
    this.heartbeatTimer = setInterval(() => {
      this.missedHeartbeats++;
      if (this.missedHeartbeats >= HEARTBEAT_MISS_THRESHOLD) {
        // No server activity for 2 intervals (30s) -- mark degraded
        if (appState.connection === 'connected') {
          setStatus('degraded');
        }
      }
    }, HEARTBEAT_INTERVAL);
  }

  private async attemptReconnect(): Promise<void> {
    if (this.retryCount >= MAX_RETRIES) {
      setStatus('disconnected');
      return;
    }

    setStatus('reconnecting');

    // Exponential backoff with jitter: base * 2^attempt * random(0.5-1.0)
    const delay = Math.min(BASE_DELAY * Math.pow(2, this.retryCount), MAX_DELAY);
    const jitter = delay * (0.5 + Math.random() * 0.5);

    this.reconnectTimer = setTimeout(async () => {
      this.retryCount++;

      try {
        setHandlers({
          onMessage: (msg) => this.handleMessage(msg),
          onBinary: (data) => this.handleBinary(data),
          onClose: () => this.handleClose(),
        });

        await connectToSei(this.url);

        // Reconnect success -- clear chat for fresh history per CLIENT-06
        updateState({ messages: [] });
        setStatus('connected');
        this.retryCount = 0;
        this.startHeartbeat();
      } catch {
        // Retry again
        this.attemptReconnect();
      }
    }, jitter);
  }

  private clearTimers(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

function setStatus(status: ConnectionStatus): void {
  updateState({ connection: status });
}

// Singleton instance
export const connectionManager = new ConnectionManager();
