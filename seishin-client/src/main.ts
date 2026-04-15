import { onStateChange, appState } from './state.ts';
import { renderConnectScreen, hideConnectScreen, showConnectScreen } from './ui/connect-screen.ts';
import { renderStatus } from './ui/status.ts';

declare const __SEI_AUTH_TOKEN__: string;
export const AUTH_TOKEN: string = __SEI_AUTH_TOKEN__;

// Main app container for post-connection content
let mainContainer: HTMLDivElement | null = null;

function initApp(): void {
  const app = document.getElementById('app');
  if (!app) return;

  // Render connect screen
  renderConnectScreen(app);

  // Render status indicator (always visible)
  renderStatus(app);

  // Create main container (hidden until connected)
  mainContainer = document.createElement('div');
  mainContainer.id = 'main-layout';
  mainContainer.style.cssText = 'display:none; flex:1; flex-direction:column; padding:16px;';
  app.appendChild(mainContainer);

  // Track previous connection state for transitions
  let wasConnected = false;

  onStateChange((state) => {
    if (state.connection === 'connected' && !wasConnected) {
      hideConnectScreen();
      if (mainContainer) mainContainer.style.display = 'flex';
      wasConnected = true;
    } else if (state.connection === 'disconnected' && wasConnected) {
      showConnectScreen();
      if (mainContainer) mainContainer.style.display = 'none';
      wasConnected = false;
    }
  });
}

document.addEventListener('DOMContentLoaded', initApp);
