import './styles.css';
import { onStateChange, appState, updateState } from './state.ts';
import { renderConnectScreen, hideConnectScreen, showConnectScreen } from './ui/connect-screen.ts';
import { renderStatus } from './ui/status.ts';
import { renderLayout } from './ui/layout.ts';
import { initPlayback, clearPlayback } from './audio/playback.ts';
import { initOrchestrator } from './orchestrator.ts';
import { startWhisperServer, stopWhisperServer } from './asr/whisper.ts';
import { startVAD, stopVAD } from './audio/vad.ts';
import { stopWaveform } from './audio/waveform.ts';

declare const __SEI_AUTH_TOKEN__: string;
export const AUTH_TOKEN: string = __SEI_AUTH_TOKEN__;

const WHISPER_MODEL_PATH = 'models/ggml-base.en.bin';

// Main app container for post-connection layout
let mainContainer: HTMLDivElement | null = null;

async function onConnected(): Promise<void> {
  hideConnectScreen();
  if (mainContainer) mainContainer.style.display = 'flex';

  // Initialize audio playback (creates AudioContext + AudioWorklet)
  await initPlayback();

  // Wire orchestrator into ConnectionManager message/binary callbacks
  initOrchestrator();

  // Start whisper.cpp sidecar for local ASR
  try {
    await startWhisperServer(WHISPER_MODEL_PATH);
  } catch (err) {
    console.error('Failed to start whisper server:', err);
  }

  // Render the full layout (chat, metrics, waveform) into main container
  if (mainContainer) {
    renderLayout(mainContainer);
  }

  // Start VAD microphone capture
  try {
    await startVAD();
  } catch (err) {
    console.error('Failed to start VAD:', err);
  }
}

async function onDisconnected(): Promise<void> {
  // Tear down active subsystems
  await stopVAD();
  await stopWhisperServer();
  stopWaveform();
  clearPlayback();

  // Reset generation state
  updateState({ isGenerating: false, interimTranscript: '' });

  // Show connect screen
  showConnectScreen();
  if (mainContainer) mainContainer.style.display = 'none';
}

function initApp(): void {
  const app = document.getElementById('app');
  if (!app) return;

  // Render connect screen (shown by default)
  renderConnectScreen(app);

  // Status indicator (always visible, fixed position over both screens)
  renderStatus(app);

  // Create main container (hidden until connected)
  mainContainer = document.createElement('div');
  mainContainer.id = 'main-layout';
  mainContainer.style.display = 'none';
  app.appendChild(mainContainer);

  // Track previous connection state for transitions
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
