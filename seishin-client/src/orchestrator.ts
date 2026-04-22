import { connectionManager } from './net/connection.ts';
import { updateState, addMessage, appState } from './state.ts';
import { markResponseComplete, markResponseInterrupted } from './ui/chat.ts';
import { SeiMessage, SeiLocalOpCommandMessage, SeiEmailListMessage, SeiGmailAuthStatusMessage, EmailResult, ReportLogEntry } from './types.ts';
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
        const isEmailOp = /\b(email|emails|inbox|unread|gmail|messages?|check mail|read mail)\b/i.test(cmd.user_text);
        // Detect if user explicitly asked for a non-primary category/label so we
        // don't override their intent (promotions/updates/social/all mail/etc).
        const explicitCategory = /\b(promotions?|updates?|social|forums?|spam|trash|all (mail|inbox)|every (mail|email)|unread|starred|important)\b/i.test(cmd.user_text);
        const inboxFilter = explicitCategory ? '' : ' Default to the PRIMARY inbox only (use query "in:inbox category:primary") unless the user explicitly asked for a different category.';
        const emailCardInstruction = ' At the end of your reply, also emit a fenced block exactly like: ```json-email-cards\n[{"id":"...", "sender":"...", "subject":"...", "snippet":"...", "timestamp":"..."}, ...]\n``` with one entry per message.';
        const agentPrompt = isEmailOp
          ? `Use the gog Gmail skill to handle this request. For listing emails use: gog gmail messages search with appropriate query. For reading content use --include-body flag.${inboxFilter}${emailCardInstruction} Request: ${cmd.user_text}`
          : cmd.user_text;
        const agentResult = await invokeOpenClawAgent(agentPrompt, { timeoutMs: 300_000 });
        if (agentResult && agentResult.trim().length > 0) {
          let agentTextForRephrase = agentResult;

          // Parse structured email cards from fenced block if this is an email op
          if (isEmailOp) {
            const fenceMatch = agentResult.match(/```json-email-cards\s*([\s\S]*?)```/);
            if (fenceMatch) {
              try {
                const parsed = JSON.parse(fenceMatch[1]);
                if (Array.isArray(parsed)) {
                  const validated: EmailResult[] = parsed.filter(
                    (r: unknown): r is EmailResult =>
                      typeof r === 'object' && r !== null &&
                      typeof (r as Record<string, unknown>).id === 'string' &&
                      typeof (r as Record<string, unknown>).sender === 'string' &&
                      typeof (r as Record<string, unknown>).subject === 'string' &&
                      typeof (r as Record<string, unknown>).snippet === 'string' &&
                      typeof (r as Record<string, unknown>).timestamp === 'string'
                  );
                  console.log('[local_op] parsed email cards:', validated.length);
                  updateState({ emailResults: validated });
                } else {
                  console.warn('[local_op] json-email-cards block is not an array');
                  updateState({ emailResults: [] });
                }
              } catch (parseErr) {
                console.warn('[local_op] failed to parse json-email-cards:', parseErr);
                updateState({ emailResults: [] });
              }
              // Strip the fenced block so it doesn't leak into the spoken rephrase
              agentTextForRephrase = agentResult.replace(/```json-email-cards\s*[\s\S]*?```/, '').trim();
            } else {
              // No fenced block found — clear cards, agent_text still flows
              updateState({ emailResults: [] });
            }
          }

          await sendRaw(JSON.stringify({ type: 'local_op_results', results: [], agent_text: agentTextForRephrase }));
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
