import { renderChat } from './chat.ts';
import { renderMetrics } from './metrics.ts';
import { initWaveform } from '../audio/waveform.ts';
import { onStateChange } from '../state.ts';

/**
 * Render the main app layout per D-17 (all elements visible simultaneously).
 * Status pill is rendered at app level (fixed position, always visible).
 *
 * Layout:
 * +------------------------------------------+
 * | [Status Pill - fixed]          [Metrics]  |
 * |-----------------------------------------|
 * |                                          |
 * |             Chat Messages                |
 * |             (scrollable)                 |
 * |                                          |
 * |-----------------------------------------|
 * |          [Waveform Canvas]               |
 * |-----------------------------------------|
 * | [Interim transcript / Listening]         |
 * +------------------------------------------+
 */
export function renderLayout(parent: HTMLElement): HTMLCanvasElement {
  // Clear previous content
  while (parent.firstChild) {
    parent.removeChild(parent.firstChild);
  }

  // Top bar: metrics (right-aligned, status pill is fixed-position at app level)
  const topBar = document.createElement('div');
  topBar.className = 'top-bar';

  const metricsContainer = document.createElement('div');
  metricsContainer.className = 'metrics-container';
  renderMetrics(metricsContainer);
  topBar.appendChild(metricsContainer);

  parent.appendChild(topBar);

  // Chat area (scrollable, takes remaining space)
  const chatArea = document.createElement('div');
  chatArea.className = 'chat-area';
  renderChat(chatArea);
  parent.appendChild(chatArea);

  // Waveform canvas bar (fixed height)
  const waveformBar = document.createElement('div');
  waveformBar.className = 'waveform-bar';

  const canvas = document.createElement('canvas');
  canvas.id = 'waveform-canvas';
  canvas.className = 'waveform-canvas';
  canvas.width = 800;
  canvas.height = 80;
  waveformBar.appendChild(canvas);
  parent.appendChild(waveformBar);

  // Initialize waveform visualization on the canvas
  initWaveform(canvas);

  // Mic toggle button
  const micBtn = document.createElement('button');
  micBtn.id = 'mic-btn';
  micBtn.className = 'mic-btn';
  micBtn.title = 'Toggle microphone';

  // Build mic SVG icon via DOM (no innerHTML)
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', '24');
  svg.setAttribute('height', '24');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  const p1 = document.createElementNS(svgNS, 'path');
  p1.setAttribute('d', 'M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z');
  const p2 = document.createElementNS(svgNS, 'path');
  p2.setAttribute('d', 'M19 10v2a7 7 0 0 1-14 0v-2');
  const l1 = document.createElementNS(svgNS, 'line');
  l1.setAttribute('x1', '12'); l1.setAttribute('y1', '19');
  l1.setAttribute('x2', '12'); l1.setAttribute('y2', '23');
  const l2 = document.createElementNS(svgNS, 'line');
  l2.setAttribute('x1', '8'); l2.setAttribute('y1', '23');
  l2.setAttribute('x2', '16'); l2.setAttribute('y2', '23');
  svg.append(p1, p2, l1, l2);
  micBtn.appendChild(svg);

  micBtn.addEventListener('click', async () => {
    const { appState } = await import('../state.ts');
    if (appState.isListening) {
      const { stopVAD } = await import('../audio/vad.ts');
      await stopVAD();
    } else {
      const { startVAD } = await import('../audio/vad.ts');
      await startVAD();
    }
  });

  // Update mic button state reactively
  onStateChange((state) => {
    micBtn.classList.toggle('active', state.isListening);
    micBtn.classList.toggle('speaking', state.isSpeaking);
  });

  // Text input bar
  const inputBar = document.createElement('div');
  inputBar.className = 'input-bar';

  const textInput = document.createElement('input');
  textInput.type = 'text';
  textInput.className = 'text-input';
  textInput.placeholder = 'Type a message...';

  const sendBtn = document.createElement('button');
  sendBtn.className = 'send-btn';
  sendBtn.textContent = 'Send';

  const sendHandler = async () => {
    const text = textInput.value.trim();
    if (!text) return;
    textInput.value = '';
    const { addMessage, updateState, appState, resetLatency } = await import('../state.ts');
    const { setMessageSentTimestamp } = await import('../orchestrator.ts');
    const { sendMessage } = await import('../net/websocket.ts');
    resetLatency();
    addMessage({ role: 'user', text });
    setMessageSentTimestamp(performance.now());
    await sendMessage(text);
    updateState({ isGenerating: true });
  };

  sendBtn.addEventListener('click', sendHandler);
  textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendHandler();
  });

  inputBar.appendChild(micBtn);
  inputBar.appendChild(textInput);
  inputBar.appendChild(sendBtn);
  parent.appendChild(inputBar);

  return canvas;
}
