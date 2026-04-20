// Connection states per D-04
export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'degraded' | 'reconnecting';

// Sei Engine incoming message types (from sei_engine.py protocol)
export type SeiMessageType = 'sentence' | 'done' | 'interrupted' | 'error' | 'transcript' | 'report_log';
export interface SeiSentenceMessage { type: 'sentence'; text: string; }
export interface SeiDoneMessage { type: 'done'; }
export interface SeiInterruptedMessage { type: 'interrupted'; }
export interface SeiErrorMessage { type: 'error'; message: string; }
export interface SeiTranscriptMessage { type: 'transcript'; text: string; }
export interface ClaudeInteraction {
  step: string;
  model?: string;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number | null;
  system?: string;
  user_message?: string;
  response?: string;
}
export interface SeiReportLogMessage {
  type: 'report_log';
  query: string;
  sql: string;
  row_count: number;
  results: Record<string, unknown>[];
  summary: string;
  claude_interactions?: ClaudeInteraction[];
  dashboard_b64?: string;
}
export interface SeiLocalOpCommandMessage {
  type: 'local_op_command';
  user_text: string;
  exhaustive?: boolean;
}
export type SeiMessage =
  | SeiSentenceMessage
  | SeiDoneMessage
  | SeiInterruptedMessage
  | SeiErrorMessage
  | SeiTranscriptMessage
  | SeiReportLogMessage
  | SeiLocalOpCommandMessage;

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

export interface FileResult {
  name: string;
  path: string;
  dir: string;
  modified_iso: string;
  modified_label: string;
  size_bytes: number;
  file_type: string;
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
  fileResults: FileResult[];  // Latest file search results from OpenClaw
}

// Report log entry — one per completed report run
export interface ReportLogEntry {
  id: string;
  query: string;
  sql: string;
  rowCount: number;
  results: Record<string, unknown>[];
  summary: string;
  claudeInteractions: ClaudeInteraction[];
  dashboardB64: string;
  timestamp: number;
}

// Event callbacks for state changes
export type StateListener = (state: AppState) => void;
