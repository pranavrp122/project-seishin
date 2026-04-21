import { onStateChange, appState } from '../state.ts';

let connectBtn: HTMLButtonElement | null = null;

/** Render a Connect Gmail button. Updates label based on gmailConnected state. */
export function renderGmailConnect(parent: HTMLElement): void {
  connectBtn = document.createElement('button');
  connectBtn.className = 'gmail-connect-btn';
  updateButtonLabel(appState.gmailConnected);
  connectBtn.addEventListener('click', handleConnect);
  parent.appendChild(connectBtn);

  onStateChange((state) => updateButtonLabel(state.gmailConnected));
}

async function handleConnect(): Promise<void> {
  try {
    // Tell sei_engine to start the OAuth flow — it opens the browser and saves the token
    const { sendMessage } = await import('../net/websocket.ts');
    await sendMessage('__gmail_oauth_start__');
  } catch (err) {
    console.error('[gmail-connect] OAuth start failed:', err);
  }
}

function updateButtonLabel(connected: boolean): void {
  if (!connectBtn) return;
  if (connected) {
    connectBtn.textContent = 'Connected \u2713';
    connectBtn.classList.add('gmail-connected');
  } else {
    connectBtn.textContent = 'Connect Gmail';
    connectBtn.classList.remove('gmail-connected');
  }
}
