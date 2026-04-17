import { connectionManager } from './net/connection.ts';
import { enqueuePCM, clearPlayback, getPlaybackPosition, resumePlayback } from './audio/playback.ts';
import { updateState, addMessage, appState } from './state.ts';
import { showSentence, markResponseComplete, markResponseInterrupted } from './ui/chat.ts';
import { SeiMessage, ReportLogEntry } from './types.ts';
import { addReportLogEntry } from './ui/report-log.ts';

interface PendingSentence {
  text: string;
  byteOffset: number; // writeIdx at time sentence frame arrived
}

let pendingSentences: PendingSentence[] = [];
let currentSentenceIdx = 0;
let firstSentenceReceived = false;
let messageSentAt = 0; // Set externally by VAD onSpeechEnd
let syncIntervalId: number | null = null;

/** Called by VAD before sendMessage to enable TTFT timing */
export function setMessageSentTimestamp(t: number): void {
  messageSentAt = t;
}

/**
 * Wire orchestrator handlers into the ConnectionManager.
 * ConnectionManager owns the WebSocket lifecycle and calls setHandlers itself,
 * delegating to onSeiMessage/onSeiBinary. We hook into those callbacks.
 */
export function initOrchestrator(): void {
  connectionManager.onSeiMessage = handleControlFrame;
  connectionManager.onSeiBinary = handleAudioChunk;
}

function handleControlFrame(msg: SeiMessage): void {
  switch (msg.type) {
    case 'transcript': {
      // Server-side ASR result — display as user message and mark generating
      const asrMs = messageSentAt > 0 ? performance.now() - messageSentAt : null;
      updateState({
        interimTranscript: '',
        isGenerating: true,
        latency: { ...appState.latency, asrMs },
      });
      addMessage({ role: 'user', text: msg.text });
      break;
    }
    case 'sentence': {
      const pos = getPlaybackPosition();
      pendingSentences.push({ text: msg.text, byteOffset: pos.writeIdx });
      if (!firstSentenceReceived) {
        firstSentenceReceived = true;
        const ttftMs = messageSentAt > 0 ? performance.now() - messageSentAt : null;
        updateState({ latency: { ...appState.latency, ttftMs } });
        startSyncPolling();
      }
      // Add companion message in 'pending' state (not shown in chat yet per D-11)
      addMessage({ role: 'companion', text: msg.text, audioState: 'pending' });
      break;
    }
    case 'done': {
      updateState({ isGenerating: false });
      const totalMs = messageSentAt > 0 ? performance.now() - messageSentAt : null;
      updateState({ latency: { ...appState.latency, totalMs } });
      // Show any remaining pending sentences immediately (audio may be buffered)
      flushPendingSentences();
      markResponseComplete();
      resetOrchestratorState();
      break;
    }
    case 'interrupted': {
      updateState({ isGenerating: false });
      clearPlayback();
      markResponseInterrupted();
      resetOrchestratorState();
      break;
    }
    case 'error': {
      console.error('Server error:', msg.message);
      updateState({ isGenerating: false });
      resetOrchestratorState();
      break;
    }
    case 'report_log': {
      const entry: ReportLogEntry = {
        id: Date.now().toString(),
        query: msg.query,
        sql: msg.sql,
        rowCount: msg.row_count,
        results: msg.results,
        summary: msg.summary,
        timestamp: Date.now(),
      };
      addReportLogEntry(entry);
      break;
    }
  }
}

function handleAudioChunk(data: Uint8Array): void {
  // Resume AudioContext on first audio (user gesture requirement)
  resumePlayback();
  enqueuePCM(data);

  // Track first audio for TTS latency
  if (firstSentenceReceived && appState.latency.ttsMs === null) {
    const ttsMs = messageSentAt > 0
      ? performance.now() - messageSentAt - (appState.latency.ttftMs || 0)
      : null;
    updateState({ latency: { ...appState.latency, ttsMs } });
  }
}

/** Poll playback position and show sentences when audio catches up per D-11 */
function startSyncPolling(): void {
  if (syncIntervalId !== null) return;
  syncIntervalId = window.setInterval(() => {
    const pos = getPlaybackPosition();
    while (currentSentenceIdx < pendingSentences.length) {
      const s = pendingSentences[currentSentenceIdx];
      if (pos.readIdx >= s.byteOffset) {
        showSentence(currentSentenceIdx, s.text);
        currentSentenceIdx++;
      } else {
        break;
      }
    }
    // Stop polling when all sentences shown and buffer is drained
    if (currentSentenceIdx >= pendingSentences.length && pos.readIdx >= pos.writeIdx) {
      stopSyncPolling();
    }
  }, 50); // 50ms polling = 20fps sync check
}

function stopSyncPolling(): void {
  if (syncIntervalId !== null) {
    clearInterval(syncIntervalId);
    syncIntervalId = null;
  }
}

function flushPendingSentences(): void {
  while (currentSentenceIdx < pendingSentences.length) {
    showSentence(currentSentenceIdx, pendingSentences[currentSentenceIdx].text);
    currentSentenceIdx++;
  }
}

function resetOrchestratorState(): void {
  pendingSentences = [];
  currentSentenceIdx = 0;
  firstSentenceReceived = false;
  messageSentAt = 0;
  stopSyncPolling();
}
