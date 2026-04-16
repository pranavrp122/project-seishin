import { connectionManager } from '../net/connection.ts';
import { onStateChange } from '../state.ts';

const SERVER_URL_KEY = 'seishin.serverUrl';

let connectEl: HTMLDivElement | null = null;
let urlInput: HTMLInputElement | null = null;
let connectBtn: HTMLButtonElement | null = null;
let errorMsg: HTMLDivElement | null = null;

export function renderConnectScreen(parent: HTMLElement): void {
  connectEl = document.createElement('div');
  connectEl.id = 'connect-screen';
  connectEl.style.cssText = `
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex: 1;
    gap: 16px;
    padding: 32px;
  `;

  const title = document.createElement('h1');
  title.textContent = 'Seishin';
  title.style.cssText = 'font-size: 28px; font-weight: 600; color: #e0e0e6; margin-bottom: 8px;';
  connectEl.appendChild(title);

  const subtitle = document.createElement('p');
  subtitle.textContent = 'Connect to your companion server';
  subtitle.style.cssText = 'font-size: 14px; color: #8888a0; margin-bottom: 24px;';
  connectEl.appendChild(subtitle);

  const form = document.createElement('div');
  form.style.cssText = 'display: flex; gap: 8px; width: 100%; max-width: 480px;';

  urlInput = document.createElement('input');
  urlInput.type = 'text';
  urlInput.placeholder = 'wss://your-server.ngrok-free.app/';
  try {
    const saved = localStorage.getItem(SERVER_URL_KEY);
    if (saved) urlInput.value = saved;
  } catch { /* localStorage unavailable — fall through */ }
  urlInput.style.cssText = `
    flex: 1;
    padding: 10px 14px;
    border: 1px solid #2a2a3a;
    border-radius: 6px;
    background: #1a1a24;
    color: #e0e0e6;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  `;
  urlInput.addEventListener('focus', () => {
    if (urlInput) urlInput.style.borderColor = '#4a9eff';
  });
  urlInput.addEventListener('blur', () => {
    if (urlInput) urlInput.style.borderColor = '#2a2a3a';
  });
  urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleConnect();
  });
  form.appendChild(urlInput);

  connectBtn = document.createElement('button');
  connectBtn.textContent = 'Connect';
  connectBtn.style.cssText = `
    padding: 10px 20px;
    border: none;
    border-radius: 6px;
    background: #4a9eff;
    color: #fff;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.2s;
    white-space: nowrap;
  `;
  connectBtn.addEventListener('click', handleConnect);
  form.appendChild(connectBtn);

  connectEl.appendChild(form);

  errorMsg = document.createElement('div');
  errorMsg.style.cssText = 'color: #ff6b6b; font-size: 13px; max-width: 480px; text-align: center; display: none;';
  connectEl.appendChild(errorMsg);

  parent.appendChild(connectEl);

  // React to connection state changes
  onStateChange((state) => {
    if (!connectBtn || !urlInput) return;

    if (state.connection === 'connecting') {
      connectBtn.textContent = 'Connecting...';
      connectBtn.disabled = true;
      connectBtn.style.background = '#3a3a4a';
      connectBtn.style.cursor = 'not-allowed';
      urlInput.disabled = true;
    } else if (state.connection === 'disconnected') {
      connectBtn.textContent = 'Connect';
      connectBtn.disabled = false;
      connectBtn.style.background = '#4a9eff';
      connectBtn.style.cursor = 'pointer';
      urlInput.disabled = false;
    }
  });
}

async function handleConnect(): Promise<void> {
  if (!urlInput || !connectBtn) return;

  const url = urlInput.value.trim();
  if (!url) {
    showError('Please enter a server URL');
    return;
  }

  // Basic URL validation
  if (!url.startsWith('ws://') && !url.startsWith('wss://')) {
    showError('URL must start with ws:// or wss://');
    return;
  }

  hideError();

  try {
    await connectionManager.connect(url);
    try { localStorage.setItem(SERVER_URL_KEY, url); } catch { /* ignore */ }
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Connection failed';
    showError(message);
  }
}

function showError(msg: string): void {
  if (errorMsg) {
    errorMsg.textContent = msg;
    errorMsg.style.display = 'block';
  }
}

function hideError(): void {
  if (errorMsg) {
    errorMsg.style.display = 'none';
  }
}

export function hideConnectScreen(): void {
  if (connectEl) connectEl.style.display = 'none';
}

export function showConnectScreen(): void {
  if (connectEl) connectEl.style.display = 'flex';
  // Keep the last-used URL visible across reconnects.
  if (urlInput && !urlInput.value) {
    try {
      const saved = localStorage.getItem(SERVER_URL_KEY);
      if (saved) urlInput.value = saved;
    } catch { /* ignore */ }
  }
  hideError();
}
