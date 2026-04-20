import WebSocket from '@tauri-apps/plugin-websocket';
import { SeiMessage } from '../types.ts';
import { AUTH_TOKEN } from '../main.ts';

type MessageHandler = (msg: SeiMessage) => void;
type BinaryHandler = (data: Uint8Array) => void;
type CloseHandler = () => void;

let ws: WebSocket | null = null;
let onMessage: MessageHandler | null = null;
let onBinary: BinaryHandler | null = null;
let onClose: CloseHandler | null = null;

export function setHandlers(opts: {
  onMessage: MessageHandler;
  onBinary: BinaryHandler;
  onClose: CloseHandler;
}): void {
  onMessage = opts.onMessage;
  onBinary = opts.onBinary;
  onClose = opts.onClose;
}

export async function connectToSei(url: string): Promise<void> {
  ws = await WebSocket.connect(url, {
    headers: { Authorization: `Bearer ${AUTH_TOKEN}` },
  });

  ws.addListener((msg) => {
    if (msg.type === 'Text' && msg.data && onMessage) {
      try {
        onMessage(JSON.parse(msg.data as string));
      } catch {
        // Ignore malformed JSON
      }
    } else if (msg.type === 'Binary' && msg.data && onBinary) {
      onBinary(new Uint8Array(msg.data as number[]));
    } else if (msg.type === 'Close') {
      onClose?.();
    }
  });
}

export async function sendMessage(text: string): Promise<void> {
  if (!ws) throw new Error('Not connected');
  await ws.send(JSON.stringify({ type: 'message', text }));
}

/** Send a pre-serialized JSON string directly over the WebSocket. */
export async function sendRaw(json: string): Promise<void> {
  if (!ws) throw new Error('Not connected');
  await ws.send(json);
}

export async function sendPCMChunk(pcm: ArrayBuffer): Promise<void> {
  if (!ws) return;
  await ws.send(Array.from(new Uint8Array(pcm)));
}

export async function sendSpeechStart(): Promise<void> {
  if (!ws) return;
  await ws.send(JSON.stringify({ type: 'speech_start' }));
}

export async function sendSpeechEnd(): Promise<void> {
  if (!ws) return;
  await ws.send(JSON.stringify({ type: 'speech_end' }));
}

export async function sendStop(): Promise<void> {
  if (!ws) return;
  await ws.send(JSON.stringify({ type: 'stop' }));
}

export async function disconnect(): Promise<void> {
  if (ws) {
    await ws.disconnect();
    ws = null;
  }
}
