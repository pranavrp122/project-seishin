/**
 * OpenClaw gateway module — reusable integration point for all OpenClaw features.
 *
 * Local operations (file search, email, calendar, browser, push, etc.) flow through
 * OpenClaw's native agent loop via POST /v1/responses. OpenClaw routes to the right
 * skill/tool based on user text — we do not classify sub-intents ourselves.
 *
 * OpenClaw runs inside WSL2. The Tauri shell plugin spawns `wsl` which runs
 * `openclaw gateway run`. Health checks and API calls go through 127.0.0.1
 * (WSL2 mirrored networking exposes WSL ports to Windows).
 */

import { Command, Child } from '@tauri-apps/plugin-shell';
import { fetch } from '@tauri-apps/plugin-http';

declare const __OPENCLAW_TOKEN__: string;

const OPENCLAW_PORT = 18789;
const OPENCLAW_BASE = `http://127.0.0.1:${OPENCLAW_PORT}`;
const OPENCLAW_HEALTH_URL = `${OPENCLAW_BASE}/health`;
const OPENCLAW_RESPONSES_URL = `${OPENCLAW_BASE}/v1/responses`;
const HEALTH_POLL_INTERVAL_MS = 500;
const HEALTH_POLL_TIMEOUT_MS = 60_000;
const AGENT_CALL_TIMEOUT_MS = 60_000;

export type OpenClawStatus = 'stopped' | 'starting' | 'healthy' | 'failed';

export interface FileSearchResult {
  name: string;
  path: string;
  dir: string;
  modified_iso: string;
  modified_label: string;
  size_bytes: number;
  file_type: string;
}

let childProcess: Child | null = null;
let status: OpenClawStatus = 'stopped';
let statusListeners: Array<(s: OpenClawStatus) => void> = [];

function setStatus(s: OpenClawStatus): void {
  status = s;
  statusListeners.forEach(fn => fn(s));
}

export function getOpenClawStatus(): OpenClawStatus {
  return status;
}

export function onOpenClawStatusChange(fn: (s: OpenClawStatus) => void): () => void {
  statusListeners.push(fn);
  return () => {
    const i = statusListeners.indexOf(fn);
    if (i >= 0) statusListeners.splice(i, 1);
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// OpenClaw agent invocation (Task 1)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Invoke OpenClaw's agent via POST /v1/responses with tools enabled.
 * OpenClaw's agent loop auto-injects installed skills + core tools (shell_exec,
 * memory_*, etc). Bearer-token auth → senderIsOwner=true → owner-only tools unlocked.
 *
 * Returns the final assistant message text. Structured output (JSON) should be
 * embedded in the text by the agent per the instruction prompt.
 */
export async function invokeOpenClawAgent(
  userText: string,
  opts?: { agent?: string; timeoutMs?: number }
): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts?.timeoutMs ?? AGENT_CALL_TIMEOUT_MS);
  try {
    const resp = await fetch(OPENCLAW_RESPONSES_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${__OPENCLAW_TOKEN__}`,
        'X-OpenClaw-Agent-Id': opts?.agent ?? 'default',
      },
      body: JSON.stringify({
        model: `openclaw/${opts?.agent ?? 'default'}`,
        input: [{ type: 'message', role: 'user', content: userText }],
        tools: [],
        stream: false,
      }),
      signal: controller.signal,
    });
    if (!resp.ok) {
      const body = await resp.text().catch(() => '');
      throw new Error(`OpenClaw /v1/responses ${resp.status}: ${body.slice(0, 200)}`);
    }
    const data = await resp.json();
    return extractAssistantText(data);
  } finally {
    clearTimeout(timer);
  }
}

/** Extract the final assistant message text from a /v1/responses JSON body. */
function extractAssistantText(data: unknown): string {
  if (!data || typeof data !== 'object') return '';
  const d = data as Record<string, unknown>;
  // Preferred: `output_text` convenience field if OpenClaw emits it
  if (typeof d.output_text === 'string') return d.output_text;
  // OpenAI Responses shape: { output: [{ type: 'message', content: [{ type: 'output_text', text: '...' }] }] }
  const output = d.output as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(output)) {
    const parts: string[] = [];
    for (const item of output) {
      if (item.type !== 'message') continue;
      const content = item.content as Array<Record<string, unknown>> | undefined;
      if (!Array.isArray(content)) continue;
      for (const c of content) {
        if (typeof c.text === 'string') parts.push(c.text);
      }
    }
    if (parts.length) return parts.join('\n');
  }
  // Fallback: OpenAI chat-completions shape
  const choices = d.choices as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(choices) && choices[0]) {
    const msg = choices[0].message as Record<string, unknown> | undefined;
    if (msg && typeof msg.content === 'string') return msg.content;
  }
  return '';
}

// ─────────────────────────────────────────────────────────────────────────────
// File search — agent-first, shell fallback (Task 2)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Search files for a user request. Prefers OpenClaw's agent (uses its native
 * skill routing + shell_exec tool). Falls back to a direct WSL find if the agent
 * call fails, the gateway is down, or the agent doesn't return parseable results.
 */
export async function searchFilesForUserText(
  userText: string,
  opts?: { exhaustive?: boolean }
): Promise<FileSearchResult[]> {
  const exhaustive = !!opts?.exhaustive;
  try {
    const results = await searchFilesViaAgent(userText, exhaustive);
    if (results.length > 0) {
      console.log(`[file search] OpenClaw agent returned ${results.length} result(s)`);
      return rankAndTrim(results, userText, exhaustive);
    }
    console.warn('[file search] agent returned no results; trying shell fallback');
  } catch (err) {
    console.warn('[file search] agent failed, falling back to direct WSL find:', err);
  }
  const fallback = await searchFilesViaShell(userText, exhaustive);
  console.log(`[file search] shell fallback returned ${fallback.length} result(s)`);
  return rankAndTrim(fallback, userText, exhaustive);
}

/**
 * Call OpenClaw's agent with an explicit instruction to search for files and
 * return results as a JSON array. The agent uses its shell_exec tool internally.
 */
async function searchFilesViaAgent(userText: string, exhaustive: boolean): Promise<FileSearchResult[]> {
  const maxResults = exhaustive ? 300 : 100;
  const prompt =
    `The user said: "${userText}"\n\n` +
    `Task: search the user's Windows files (accessible from WSL at /mnt/c/Users/$(whoami | tr -d '\\r')/...). ` +
    `Search Downloads, Documents, and OneDrive directories with maxdepth 5. ` +
    `Skip junk paths: node_modules, .git, .venv, __pycache__, build, dist, .next, .cache, target, AppData, .vscode, .idea.\n\n` +
    `Output ONLY a JSON array (no prose, no markdown fences, no explanation) of up to ${maxResults} matching files, ` +
    `each with exactly these keys: name, path, dir, modified_iso, modified_label, size_bytes, file_type. ` +
    `Example of modified_label: "3 days ago", "yesterday", "1 months ago". ` +
    `Sort by relevance (filename-keyword match) then by modification time (newest first). ` +
    `If nothing matches return [].`;
  const raw = await invokeOpenClawAgent(prompt);
  return parseJsonFileList(raw);
}

function parseJsonFileList(raw: string): FileSearchResult[] {
  if (!raw) return [];
  // Strip markdown fences if present
  const cleaned = raw
    .replace(/^```(?:json)?\s*/i, '')
    .replace(/\s*```\s*$/, '')
    .trim();
  // Find the first JSON array in the text
  const firstBracket = cleaned.indexOf('[');
  const lastBracket = cleaned.lastIndexOf(']');
  if (firstBracket < 0 || lastBracket <= firstBracket) return [];
  const slice = cleaned.slice(firstBracket, lastBracket + 1);
  try {
    const parsed = JSON.parse(slice);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(item =>
      item && typeof item === 'object' &&
      typeof item.name === 'string' &&
      typeof item.path === 'string'
    ).map(item => ({
      name: String(item.name),
      path: String(item.path),
      dir: String(item.dir ?? item.path.substring(0, item.path.lastIndexOf('/'))),
      modified_iso: String(item.modified_iso ?? ''),
      modified_label: String(item.modified_label ?? ''),
      size_bytes: Number(item.size_bytes ?? 0) || 0,
      file_type: String(item.file_type ?? item.name.split('.').pop()?.toLowerCase() ?? ''),
    }));
  } catch {
    return [];
  }
}

/**
 * Direct WSL find fallback. Used when the OpenClaw agent is unavailable or fails.
 * Extracts keywords from the raw user text by stripping stop words.
 */
async function searchFilesViaShell(userText: string, exhaustive: boolean): Promise<FileSearchResult[]> {
  const keywordList = extractKeywords(userText);
  const nameConditions = keywordList.length > 0
    ? keywordList.map(k => `-iname "*${k}*"`).join(' -o ')
    : '-name "*"';
  const excludes = [
    '*/node_modules/*', '*/.git/*', '*/.venv/*', '*/venv/*', '*/__pycache__/*',
    '*/build/*', '*/dist/*', '*/.next/*', '*/.cache/*', '*/target/*',
    '*/AppData/*', '*/.vscode/*', '*/.idea/*',
  ].map(p => `-not -path "${p}"`).join(' ');
  const user = `$(whoami | tr -d '\\r')`;
  const headLimit = exhaustive ? 300 : 100;
  const findCmd =
    `find "/mnt/c/Users/${user}/Downloads" "/mnt/c/Users/${user}/Documents" "/mnt/c/Users/${user}/OneDrive"` +
    ` -maxdepth 5 -type f ${excludes} \\( ${nameConditions} \\)` +
    ` -printf "%p\\t%T@\\t%s\\n" 2>/dev/null | head -${headLimit}`;

  const output = await Command.create('wsl', ['--', 'bash', '-c', findCmd]).execute();
  if (!output.stdout.trim()) return [];

  return output.stdout.trim().split('\n').filter(Boolean).map(line => {
    const parts = line.split('\t');
    const filePath = parts[0] ?? '';
    const epochMs = parseFloat(parts[1] ?? '0') * 1000;
    const sizeBytes = parseInt(parts[2] ?? '0') || 0;
    const name = filePath.split('/').pop() ?? '';
    const dir = filePath.substring(0, filePath.lastIndexOf('/'));
    const ext = name.includes('.') ? name.split('.').pop()?.toLowerCase() ?? '' : '';
    const date = new Date(epochMs);
    return {
      name,
      path: filePath,
      dir,
      modified_iso: isNaN(epochMs) ? '' : date.toISOString(),
      modified_label: isNaN(epochMs) ? '' : relativeTime(date),
      size_bytes: sizeBytes,
      file_type: ext,
    };
  });
}

/** Strip stop words and punctuation to derive search keywords from raw user text. */
function extractKeywords(userText: string): string[] {
  const stopWords = new Set([
    'find', 'search', 'look', 'for', 'the', 'a', 'an', 'my', 'me',
    'files', 'file', 'i', 'need', 'want', 'where', 'is', 'are',
    'on', 'in', 'of', 'please', 'can', 'you', 'get', 'all', 'every',
    'each', 'list', 'with', 'name', 'named', 'show', 'open',
  ]);
  return userText
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .split(/\s+/)
    .filter(w => w.length > 0 && !stopWords.has(w));
}

/** Rank by keyword-match count + phrase bonus, apply clear-winner or top-5 cap. */
function rankAndTrim(
  results: FileSearchResult[],
  userText: string,
  exhaustive: boolean,
): FileSearchResult[] {
  if (results.length === 0) return [];
  const keywordList = extractKeywords(userText);
  const phrase = keywordList.join(' ').toLowerCase();

  const scored = results.map(r => {
    const baseName = r.name.toLowerCase().replace(/\.[^.]+$/, '');
    const matched = keywordList.filter(k => baseName.includes(k)).length;
    let score = matched * 10;
    if (phrase && baseName.includes(phrase)) score += 100;
    if (keywordList.length > 0 && matched === keywordList.length) score += 30;
    if (r.size_bytes < 1024) score -= 1;
    const epoch = r.modified_iso ? new Date(r.modified_iso).getTime() : 0;
    return { r, score, matched, epoch };
  });
  scored.sort((a, b) => (b.score - a.score) || (b.epoch - a.epoch));

  if (exhaustive) return scored.map(({ r }) => r);

  const top = scored[0];
  const runnerUp = scored[1];
  const clearWinner =
    top && (!runnerUp ||
      top.matched > runnerUp.matched ||
      (top.score >= 100 && top.score >= 2 * Math.max(runnerUp.score, 1)));
  const cutoff = clearWinner ? 1 : 5;
  return scored.slice(0, cutoff).map(({ r }) => r);
}

function relativeTime(date: Date): string {
  const diff = Date.now() - date.getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days} days ago`;
  if (days < 30) return `${Math.floor(days / 7)} weeks ago`;
  if (days < 365) return `${Math.floor(days / 30)} months ago`;
  return `${Math.floor(days / 365)} years ago`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Lifecycle (unchanged from Phase 1.3)
// ─────────────────────────────────────────────────────────────────────────────

export async function startOpenClaw(): Promise<boolean> {
  if (status === 'healthy') return true;

  try {
    const probe = await fetch(OPENCLAW_HEALTH_URL);
    if (probe.ok) {
      console.log('[openclaw] reusing already-running instance');
      setStatus('healthy');
      return true;
    }
  } catch { /* not running yet, proceed to spawn */ }

  try {
    await Command.create('wsl', ['--', 'bash', '-c', 'pkill -9 -f openclaw-gateway 2>/dev/null; true']).execute();
    await new Promise(r => setTimeout(r, 1000));
  } catch { /* best-effort */ }

  setStatus('starting');

  try {
    const command = Command.create('wsl', [
      '--', 'bash', '-c',
      `. ~/.nvm/nvm.sh && openclaw gateway run --port ${OPENCLAW_PORT}`,
    ]);
    command.on('error', (err: string) => {
      console.error('[openclaw] process error:', err);
      setStatus('failed');
    });
    command.on('close', (data: { code: number | null }) => {
      console.log('[openclaw] process exited:', data.code);
      if (status !== 'stopped') setStatus('failed');
    });
    command.stdout.on('data', (line: string) => console.log('[openclaw:stdout]', line));
    command.stderr.on('data', (line: string) => console.warn('[openclaw:stderr]', line));

    childProcess = await command.spawn();
    console.log('[openclaw] spawned child process, pid:', childProcess.pid);
  } catch (err) {
    console.error('[openclaw] failed to spawn:', err);
    setStatus('failed');
    return false;
  }

  const deadline = Date.now() + HEALTH_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const resp = await fetch(OPENCLAW_HEALTH_URL);
      if (resp.ok) {
        console.log('[openclaw] health check passed');
        setStatus('healthy');
        return true;
      }
    } catch { /* expected during startup */ }
    await new Promise(r => setTimeout(r, HEALTH_POLL_INTERVAL_MS));
  }

  console.error('[openclaw] health check timed out after', HEALTH_POLL_TIMEOUT_MS, 'ms');
  setStatus('failed');
  return false;
}

export async function stopOpenClaw(): Promise<void> {
  if (childProcess) {
    try {
      await childProcess.kill();
      console.log('[openclaw] child process killed');
    } catch (err) {
      console.warn('[openclaw] kill error (may already be stopped):', err);
    }
    childProcess = null;
  }
  try {
    await Command.create('wsl', [
      '--', 'bash', '-c', 'pkill -9 -f openclaw-gateway 2>/dev/null; true',
    ]).execute();
  } catch { /* best-effort */ }
  setStatus('stopped');
}
