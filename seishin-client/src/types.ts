// Connection states per D-04
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'degraded' | 'reconnecting';

// Sei Engine incoming message types (from sei_engine.py protocol)
export type SeiMessageType = 'sentence' | 'done' | 'interrupted' | 'error' | 'transcript';
export interface SeiSentenceMessage { type: 'sentence'; text: string; }
export interface SeiDoneMessage { type: 'done'; }
export interface SeiInterruptedMessage { type: 'interrupted'; }
export interface SeiErrorMessage { type: 'error'; message: string; }
export interface SeiTranscriptMessage { type: 'transcript'; text: string; }
export type SeiMessage = SeiSentenceMessage | SeiDoneMessage | SeiInterruptedMessage | SeiErrorMessage | SeiTranscriptMessage;

// Outgoing message types
export interface SeiOutMessage { type: 'message'; text: string; }
export interface SeiStopMessage { type: 'stop'; }

// Chat message for UI per D-08, D-10, D-11
export interface ChatMessage {
  id: string;
  role: 'user' | 'companion';
  text: string;
  timestamp: number;
  // For companion messages: 'pending' = waiting for audio sync, 'playing' = audio playing, 'complete' = done
  audioState?: 'pending' | 'playing' | 'complete';
}

// Latency metrics per D-14
export interface LatencyMetrics {
  asrMs: number | null;        // whisper.cpp transcription time
  networkSendMs: number | null; // Time to send message to server
  ttftMs: number | null;       // Time to first sentence frame from server
  ttsMs: number | null;        // Time from first sentence to first audio byte
  totalMs: number | null;      // End-to-end from speech end to first audio
}

// App state
export interface AppState {
  connection: ConnectionStatus;
  serverUrl: string;
  messages: ChatMessage[];
  isListening: boolean;       // VAD is active
  isSpeaking: boolean;        // User is currently speaking
  isGenerating: boolean;      // Server is generating response
  interimTranscript: string;  // Live transcription text per D-09
  latency: LatencyMetrics;
}

// Event callbacks for state changes
export type StateListener = (state: AppState) => void;
