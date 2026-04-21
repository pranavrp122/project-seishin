import { connectionManager } from './net/connection.ts';
import { updateState, addMessage, appState } from './state.ts';
import { markResponseComplete, markResponseInterrupted } from './ui/chat.ts';
import { SeiMessage, SeiLocalOpCommandMessage, SeiEmailListMessage, SeiGmailAuthStatusMessage, ReportLogEntry } from './types.ts';
import { addReportLogEntry } from './ui/report-log.ts';
import { searchFilesForUserText, invokeOpenClawAgent } from '@openclaw/gateway.ts';
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
    case 'local_op_command': {
      const cmd = msg as SeiLocalOpCommandMessage;
      console.log('[local_op] user_text:', cmd.user_text, 'exhaustive:', !!cmd.exhaustive);
      try {
        // Route all local_op through OpenClaw agent — its LLM picks the right skill
        // (gog for email, shell_exec for files, etc). Fall back to direct file search
        // only if the agent returns nothing useful.
        console.log('[local_op] routing to OpenClaw agent');
        const agentResult = await invokeOpenClawAgent(cmd.user_text);
        if (agentResult && agentResult.trim().length > 0) {
          await sendRaw(JSON.stringify({ type: 'local_op_results', results: [], agent_text: agentResult }));
        } else {
          // Agent returned empty — fall back to file search
          console.log('[local_op] agent returned empty, falling back to file search');
          const results = await searchFilesForUserText(cmd.user_text, { exhaustive: !!cmd.exhaustive });
          updateState({ fileResults: results });
          await sendRaw(JSON.stringify({ type: 'local_op_results', results }));
        }
      } catch (err) {
        console.error('[local_op] error:', err);
        updateState({ fileResults: [] });
        await sendRaw(JSON.stringify({ type: 'local_op_results', results: [] }));
      }
      break;
    }
    case 'email_list': {
      const emailMsg = msg as SeiEmailListMessage;
      console.log('[email] received', emailMsg.emails.length, 'emails');
      updateState({ emailResults: emailMsg.emails });
      break;
    }
    case 'gmail_auth_status': {
      const authMsg = msg as SeiGmailAuthStatusMessage;
      console.log('[gmail] auth status:', authMsg.connected);
      updateState({ gmailConnected: authMsg.connected });
      break;
    }
  }
}
