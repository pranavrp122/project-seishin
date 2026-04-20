import './styles.css';
import { onStateChange, updateState, addMessage } from './state.ts';
import { renderConnectScreen, hideConnectScreen, showConnectScreen } from './ui/connect-screen.ts';
import { renderStatus } from './ui/status.ts';
import { renderLayout } from './ui/layout.ts';
import { initOrchestrator } from './orchestrator.ts';
import { startOpenClaw, stopOpenClaw } from './openclaw/gateway.ts';
import { getCurrentWindow } from '@tauri-apps/api/window';

declare const __SEI_AUTH_TOKEN__: string;
export const AUTH_TOKEN: string = __SEI_AUTH_TOKEN__;

let mainContainer: HTMLDivElement | null = null;

async function onConnected(): Promise<void> {
  hideConnectScreen();
  if (mainContainer) mainContainer.style.display = 'flex';
  initOrchestrator();
  if (mainContainer) renderLayout(mainContainer);

  // Start OpenClaw in background — don't block the UI
  startOpenClaw().then(healthy => {
    if (healthy) {
      console.log('[main] OpenClaw ready');
    } else {
      console.warn('[main] OpenClaw failed to start — file search will be unavailable');
      addMessage({ role: 'companion', text: 'Note: Local automation engine failed to start. File search may be unavailable.', audioState: 'complete' });
    }
  });
}

async function onDisconnected(): Promise<void> {
  updateState({ isGenerating: false, interimTranscript: '' });
  showConnectScreen();
  if (mainContainer) mainContainer.style.display = 'none';
}

function initApp(): void {
  const app = document.getElementById('app');
  if (!app) return;

  renderConnectScreen(app);
  renderStatus(app);

  mainContainer = document.createElement('div');
  mainContainer.id = 'main-layout';
  mainContainer.style.display = 'none';
  app.appendChild(mainContainer);

  // Clean up OpenClaw on app close — no orphaned processes
  getCurrentWindow().onCloseRequested(async () => {
    await stopOpenClaw();
  });

  let wasConnected = false;
  onStateChange((state) => {
    if (state.connection === 'connected' && !wasConnected) {
      wasConnected = true;
      onConnected();
    } else if (state.connection === 'disconnected' && wasConnected) {
      wasConnected = false;
      onDisconnected();
    }
  });
}

document.addEventListener('DOMContentLoaded', initApp);
