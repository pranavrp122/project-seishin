import { AppState, ChatMessage, StateListener } from './types.ts';

const listeners: StateListener[] = [];

export const appState: AppState = {
  connection: 'disconnected',
  serverUrl: '',
  messages: [],
  isListening: false,
  isSpeaking: false,
  isGenerating: false,
  interimTranscript: '',
  latency: { asrMs: null, networkSendMs: null, ttftMs: null, ttsMs: null, totalMs: null },
};

export function updateState(partial: Partial<AppState>): void {
  Object.assign(appState, partial);
  listeners.forEach(fn => fn(appState));
}

export function onStateChange(fn: StateListener): () => void {
  listeners.push(fn);
  return () => { const i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); };
}

export function addMessage(msg: Omit<ChatMessage, 'id' | 'timestamp'>): ChatMessage {
  const m: ChatMessage = { ...msg, id: crypto.randomUUID(), timestamp: Date.now() };
  appState.messages.push(m);
  updateState({ messages: [...appState.messages] });
  return m;
}

export function resetLatency(): void {
  updateState({ latency: { asrMs: null, networkSendMs: null, ttftMs: null, ttsMs: null, totalMs: null } });
}
