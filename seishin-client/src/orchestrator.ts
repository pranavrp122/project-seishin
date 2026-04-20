import { connectionManager } from './net/connection.ts';
import { updateState, addMessage, appState } from './state.ts';
import { markResponseComplete, markResponseInterrupted } from './ui/chat.ts';
import { SeiMessage, SeiFindFileCommandMessage, FileResult, ReportLogEntry } from './types.ts';
import { addReportLogEntry } from './ui/report-log.ts';
import { callCompletions, getOpenClawStatus } from '@openclaw/gateway.ts';
import { sendRaw } from './net/websocket.ts';

let messageSentAt = 0;

/** Called by the send handler to enable latency timing */
export function setMessageSentTimestamp(t: number): void {
  messageSentAt = t;
}

export function initOrchestrator(): void {
  connectionManager.onSeiMessage = handleControlFrame;
  connectionManager.onSeiBinary = () => {}; // ignore audio in text mode
}

async function handleControlFrame(msg: SeiMessage): Promise<void> {
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
    case 'find_file_command': {
      const query = (msg as SeiFindFileCommandMessage).query;

      if (getOpenClawStatus() !== 'healthy') {
        await sendRaw(JSON.stringify({ type: 'file_results', results: [] }));
        break;
      }

      const systemPrompt = `You are a file search assistant with shell execution tools.
Search the user's home directory for files matching their query.
Use shell commands (find, ls, or similar) to search ~/Documents, ~/Downloads, ~/Desktop, and ~ (shallow).
Return ONLY a valid JSON array, no prose, no markdown:
[{"name":"filename.ext","path":"/full/path","dir":"/containing/dir","modified_iso":"2026-01-15T10:30:00Z","modified_label":"3 days ago","size_bytes":12345,"file_type":"pdf"}]
Maximum 20 results, newest first. If nothing found return [].`;

      const queryParts: string[] = [];
      if (query.keywords) queryParts.push(`keywords: ${query.keywords}`);
      if (query.file_type) queryParts.push(`type: ${query.file_type}`);
      if (query.modified_after) queryParts.push(`modified after: ${query.modified_after}`);
      if (query.modified_before) queryParts.push(`modified before: ${query.modified_before}`);
      const userMessage = `Find files — ${queryParts.join(', ') || 'all recent files'}`;

      try {
        const raw = await callCompletions(systemPrompt, userMessage, 2048, 20000);
        const cleaned = raw.trim().replace(/^```[a-z]*\n?/, '').replace(/\n?```$/, '').trim();
        const results: FileResult[] = JSON.parse(cleaned);
        const safeResults = Array.isArray(results) ? results : [];
        updateState({ fileResults: safeResults });
        await sendRaw(JSON.stringify({ type: 'file_results', results: safeResults }));
      } catch (err) {
        console.error('[openclaw] file search error:', err);
        updateState({ fileResults: [] });
        await sendRaw(JSON.stringify({ type: 'file_results', results: [] }));
      }
      break;
    }
  }
}
