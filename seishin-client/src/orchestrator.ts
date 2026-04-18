import { connectionManager } from './net/connection.ts';
import { updateState, addMessage, appState } from './state.ts';
import { markResponseComplete, markResponseInterrupted } from './ui/chat.ts';
import { SeiMessage, ReportLogEntry } from './types.ts';
import { addReportLogEntry } from './ui/report-log.ts';

let messageSentAt = 0;

/** Called by the send handler to enable latency timing */
export function setMessageSentTimestamp(t: number): void {
  messageSentAt = t;
}

export function initOrchestrator(): void {
  connectionManager.onSeiMessage = handleControlFrame;
  connectionManager.onSeiBinary = () => {}; // ignore audio in text mode
}

function handleControlFrame(msg: SeiMessage): void {
  switch (msg.type) {
    case 'transcript': {
      updateState({ isGenerating: true });
      addMessage({ role: 'user', text: msg.text });
      break;
    }
    case 'sentence': {
      // Text mode: show immediately, no audio sync needed
      addMessage({ role: 'companion', text: msg.text, audioState: 'complete' });
      if (appState.latency.ttftMs === null && messageSentAt > 0) {
        const ttftMs = performance.now() - messageSentAt;
        updateState({ latency: { ...appState.latency, ttftMs } });
      }
      break;
    }
    case 'done': {
      updateState({ isGenerating: false });
      markResponseComplete();
      messageSentAt = 0;
      break;
    }
    case 'interrupted': {
      updateState({ isGenerating: false });
      markResponseInterrupted();
      messageSentAt = 0;
      break;
    }
    case 'error': {
      console.error('Server error:', msg.message);
      updateState({ isGenerating: false });
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
        claudeInteractions: msg.claude_interactions ?? [],
        dashboardB64: msg.dashboard_b64 ?? '',
        timestamp: Date.now(),
      };
      addReportLogEntry(entry);
      break;
    }
  }
}
