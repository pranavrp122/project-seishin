import { Command, Child } from '@tauri-apps/plugin-shell';

let serverProcess: Child | null = null;
const WHISPER_PORT = 9876;
const WHISPER_HOST = '127.0.0.1';

export async function startWhisperServer(modelPath: string): Promise<void> {
  const cmd = Command.sidecar('binaries/whisper-server', [
    '--model', modelPath,
    '--host', WHISPER_HOST,
    '--port', String(WHISPER_PORT),
    '--convert',  // Accept WAV input, convert internally
  ]);
  cmd.stdout.on('data', (line: string) => console.log('[whisper]', line));
  cmd.stderr.on('data', (line: string) => console.warn('[whisper]', line));
  serverProcess = await cmd.spawn();
  // Wait for server to be ready (poll /health or just wait)
  await waitForServer();
}

async function waitForServer(timeout = 10000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      const resp = await fetch(`http://${WHISPER_HOST}:${WHISPER_PORT}/health`);
      if (resp.ok) return;
    } catch { /* not ready yet */ }
    await new Promise(r => setTimeout(r, 200));
  }
  throw new Error('whisper-server failed to start within timeout');
}

export async function stopWhisperServer(): Promise<void> {
  if (serverProcess) { await serverProcess.kill(); serverProcess = null; }
}

export async function transcribe(wavBlob: Blob): Promise<string> {
  const form = new FormData();
  form.append('file', wavBlob, 'audio.wav');
  form.append('response_format', 'json');
  form.append('language', 'en');
  const resp = await fetch(`http://${WHISPER_HOST}:${WHISPER_PORT}/inference`, {
    method: 'POST',
    body: form,
  });
  if (!resp.ok) throw new Error(`Whisper error: ${resp.status}`);
  const data = await resp.json();
  return (data.text || '').trim();
}
