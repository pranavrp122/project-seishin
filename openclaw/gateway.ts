/**
 * OpenClaw gateway module — reusable integration point for all OpenClaw features.
 * Manages the OpenClaw sidecar lifecycle (spawn, health-poll, teardown) and provides
 * direct WSL shell execution for file operations.
 *
 * OpenClaw runs inside WSL2. The Tauri shell plugin spawns `wsl` which in turn
 * runs `openclaw gateway run`. Health checks and API calls go through
 * 127.0.0.1 (WSL2 mirrored networking exposes WSL ports to Windows).
 */

import { Command, Child } from '@tauri-apps/plugin-shell';
import { fetch } from '@tauri-apps/plugin-http';

declare const __OPENCLAW_TOKEN__: string;

const OPENCLAW_PORT = 18789;
const OPENCLAW_HEALTH_URL = `http://127.0.0.1:${OPENCLAW_PORT}/health`;
const OPENCLAW_COMPLETIONS_URL = `http://127.0.0.1:${OPENCLAW_PORT}/v1/chat/completions`;
const HEALTH_POLL_INTERVAL_MS = 500;
const HEALTH_POLL_TIMEOUT_MS = 60_000;
const DEFAULT_COMPLETIONS_TIMEOUT_MS = 15_000;

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

/**
 * Search Windows files via WSL find command.
 * Searches common Windows user directories via /mnt/c/Users/$USER mount.
 * Does not require OpenClaw to be healthy — uses direct shell execution.
 */
export async function searchFiles(query: {
  keywords?: string | null;
  file_type?: string | null;
  modified_after?: string | null;
  modified_before?: string | null;
}): Promise<FileSearchResult[]> {
  // Sanitize keywords to prevent shell injection
  const rawKeywords = (query.keywords ?? '').replace(/[^a-zA-Z0-9 ._\-]/g, '').trim();
  const fileType = (query.file_type ?? '').replace(/[^a-zA-Z0-9]/g, '').trim();

  // Build -iname conditions for each keyword (OR logic)
  const nameConditions = rawKeywords.length > 0
    ? rawKeywords.split(/\s+/).map(k => `-iname "*${k}*"`).join(' -o ')
    : '-name "*"';

  const typeCondition = fileType ? `-a -iname "*.${fileType}"` : '';

  const dateCondition = query.modified_after
    ? `-a -newermt "${query.modified_after.replace(/[^0-9\-]/g, '')}"` : '';

  const user = `$(whoami | tr -d '\\r')`;
  const findCmd =
    `find "/mnt/c/Users/${user}/Downloads" "/mnt/c/Users/${user}/Documents" "/mnt/c/Users/${user}/OneDrive"` +
    ` -maxdepth 5 -type f \\( ${nameConditions} \\) ${typeCondition} ${dateCondition}` +
    ` -printf "%p\\t%T@\\t%s\\n" 2>/dev/null | sort -t$'\\t' -k2 -rn | head -20`;

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

/**
 * Spawn `openclaw gateway run --port 18789` inside WSL2 as a child process.
 * Polls health endpoint until ready or timeout.
 * Returns true if healthy, false if failed/timed out.
 */
export async function startOpenClaw(): Promise<boolean> {
  if (status === 'healthy') return true;

  // Reuse a running instance (e.g. left over from a previous dev restart)
  try {
    const probe = await fetch(OPENCLAW_HEALTH_URL);
    if (probe.ok) {
      console.log('[openclaw] reusing already-running instance');
      setStatus('healthy');
      return true;
    }
  } catch { /* not running yet, proceed to spawn */ }

  // Kill any stale locked instance before spawning
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

  // Poll health endpoint
  const deadline = Date.now() + HEALTH_POLL_TIMEOUT_MS;
  while (Date.now() < deadline) {
    try {
      const resp = await fetch(OPENCLAW_HEALTH_URL);
      if (resp.ok) {
        console.log('[openclaw] health check passed');
        setStatus('healthy');
        return true;
      }
    } catch {
      // Expected while gateway is starting up
    }
    await new Promise(r => setTimeout(r, HEALTH_POLL_INTERVAL_MS));
  }

  console.error('[openclaw] health check timed out after', HEALTH_POLL_TIMEOUT_MS, 'ms');
  setStatus('failed');
  return false;
}

/**
 * Kill the OpenClaw child process gracefully.
 * Uses both the Tauri child handle and a WSL pkill fallback to ensure no orphans.
 */
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

  // Ensure no orphaned openclaw processes in WSL
  try {
    await Command.create('wsl', [
      '--', 'bash', '-c', 'pkill -9 -f openclaw-gateway 2>/dev/null; true',
    ]).execute();
  } catch {
    // Best-effort cleanup
  }

  setStatus('stopped');
}

/**
 * Call OpenClaw's OpenAI-compatible completions endpoint.
 * Used for future phases requiring LLM reasoning (email, calendar, etc.).
 */
export async function callCompletions(
  systemPrompt: string,
  userMessage: string,
  maxTokens: number = 2048,
  timeoutMs: number = DEFAULT_COMPLETIONS_TIMEOUT_MS,
): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const resp = await fetch(OPENCLAW_COMPLETIONS_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${__OPENCLAW_TOKEN__}`,
      },
      body: JSON.stringify({
        model: 'openclaw:main',
        messages: [
          { role: 'system', content: systemPrompt },
          { role: 'user', content: userMessage },
        ],
        max_tokens: maxTokens,
        temperature: 0.0,
      }),
      signal: controller.signal,
    });

    if (!resp.ok) {
      throw new Error(`OpenClaw completions failed: ${resp.status} ${resp.statusText}`);
    }

    const data = await resp.json();
    return data.choices?.[0]?.message?.content ?? '';
  } finally {
    clearTimeout(timer);
  }
}
