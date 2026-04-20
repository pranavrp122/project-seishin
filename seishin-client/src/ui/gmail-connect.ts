import { invoke } from '@tauri-apps/api/core';
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
    await invoke('gmail_oauth_start');
  } catch (err) {
    console.error('[gmail-connect] OAuth invoke failed:', err);
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
