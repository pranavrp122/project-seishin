/**
 * OpenClaw gateway module — reusable integration point for all OpenClaw features.
 * Manages the OpenClaw sidecar lifecycle (spawn, health-poll, teardown) and provides
 * an OpenAI-compatible completions client for local AI operations.
 *
 * OpenClaw runs inside WSL2. The Tauri shell plugin spawns `wsl` which in turn
 * runs `openclaw gateway run`. Health checks and API calls go through
 * 127.0.0.1 (WSL2 mirrored networking exposes WSL ports to Windows).
 */

import { Command, Child } from '@tauri-apps/plugin-shell';

const OPENCLAW_PORT = 18789;
const OPENCLAW_HEALTH_URL = `http://127.0.0.1:${OPENCLAW_PORT}/health`;
const OPENCLAW_COMPLETIONS_URL = `http://127.0.0.1:${OPENCLAW_PORT}/v1/chat/completions`;
const HEALTH_POLL_INTERVAL_MS = 500;
const HEALTH_POLL_TIMEOUT_MS = 60_000;
const DEFAULT_COMPLETIONS_TIMEOUT_MS = 15_000;

export type OpenClawStatus = 'stopped' | 'starting' | 'healthy' | 'failed';

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
 * Spawn `openclaw gateway run --port 18789` inside WSL2 as a child process.
 * Polls health endpoint until ready or timeout.
 * Returns true if healthy, false if failed/timed out.
 */
export async function startOpenClaw(): Promise<boolean> {
  if (status === 'healthy') return true;
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

  // Fallback: ensure no orphaned openclaw processes in WSL
  try {
    await Command.create('wsl', [
      '--', 'bash', '-c', 'pkill -f "openclaw gateway" 2>/dev/null || true',
    ]).execute();
  } catch {
    // Best-effort cleanup
  }

  setStatus('stopped');
}

/**
 * Call OpenClaw's OpenAI-compatible completions endpoint.
 * Used for local AI operations (file search, email drafting, etc.).
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
      headers: { 'Content-Type': 'application/json' },
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
