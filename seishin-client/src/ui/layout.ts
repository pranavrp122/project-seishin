import { renderChat } from './chat.ts';
import { renderMetrics } from './metrics.ts';
import { renderReportLog } from './report-log.ts';
import { initWaveform } from '../audio/waveform.ts';
import { onStateChange } from '../state.ts';

/**
 * Layout:
 * +--[≡]--+--[top-bar / metrics]--+
 * |       |                       |
 * | Panel | (waveform)            |
 * | [Chat]|                       |
 * | [Log] | (input bar)           |
 * +-------+-----------------------+
 *
 * Panel is collapsible via the toggle button.
 * Two tabs inside: Chat (conversation) and Log (report log).
 */
export function renderLayout(parent: HTMLElement): HTMLCanvasElement {
  while (parent.firstChild) parent.removeChild(parent.firstChild);

  // Root: horizontal flex
  parent.style.flexDirection = 'row';

  // ── Side panel ──────────────────────────────────────────────────────────
  const sidePanel = document.createElement('div');
  sidePanel.id = 'side-panel';
  sidePanel.className = 'side-panel open';

  // Tab bar
  const tabBar = document.createElement('div');
  tabBar.className = 'panel-tab-bar';

  const chatTabBtn = document.createElement('button');
  chatTabBtn.className = 'panel-tab-btn active';
  chatTabBtn.textContent = 'Chat';
  chatTabBtn.dataset.tab = 'chat';

  const logTabBtn = document.createElement('button');
  logTabBtn.className = 'panel-tab-btn';
  logTabBtn.textContent = 'Report Log';
  logTabBtn.dataset.tab = 'log';

  tabBar.appendChild(chatTabBtn);
  tabBar.appendChild(logTabBtn);
  sidePanel.appendChild(tabBar);

  // Chat pane
  const chatPane = document.createElement('div');
  chatPane.className = 'panel-pane active';
  chatPane.id = 'chat-pane';
  renderChat(chatPane);
  sidePanel.appendChild(chatPane);

  // Log pane
  const logPane = document.createElement('div');
  logPane.className = 'panel-pane';
  logPane.id = 'log-pane';
  renderReportLog(logPane);
  sidePanel.appendChild(logPane);

  // Tab switching
  [chatTabBtn, logTabBtn].forEach(btn => {
    btn.addEventListener('click', () => {
      [chatTabBtn, logTabBtn].forEach(b => b.classList.remove('active'));
      [chatPane, logPane].forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      const target = btn.dataset.tab === 'chat' ? chatPane : logPane;
      target.classList.add('active');
    });
  });

  parent.appendChild(sidePanel);

  // ── Main content ─────────────────────────────────────────────────────────
  const mainContent = document.createElement('div');
  mainContent.id = 'main-content';
  mainContent.className = 'main-content';

  // Top bar: toggle button + metrics
  const topBar = document.createElement('div');
  topBar.className = 'top-bar';

  // Panel toggle button
  const toggleBtn = document.createElement('button');
  toggleBtn.id = 'panel-toggle';
  toggleBtn.className = 'panel-toggle-btn';
  toggleBtn.title = 'Toggle panel';
  toggleBtn.textContent = '◀';
  toggleBtn.addEventListener('click', () => {
    const open = sidePanel.classList.toggle('open');
    toggleBtn.textContent = open ? '◀' : '▶';
  });
  topBar.appendChild(toggleBtn);

  const metricsContainer = document.createElement('div');
  metricsContainer.className = 'metrics-container';
  renderMetrics(metricsContainer);
  topBar.appendChild(metricsContainer);

  mainContent.appendChild(topBar);

  // Waveform
  const waveformBar = document.createElement('div');
  waveformBar.className = 'waveform-bar';
  const canvas = document.createElement('canvas');
  canvas.id = 'waveform-canvas';
  canvas.className = 'waveform-canvas';
  canvas.width = 800;
  canvas.height = 80;
  waveformBar.appendChild(canvas);
  mainContent.appendChild(waveformBar);
  initWaveform(canvas);

  // Mic button
  const micBtn = document.createElement('button');
  micBtn.id = 'mic-btn';
  micBtn.className = 'mic-btn';
  micBtn.title = 'Toggle microphone';
  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('width', '24'); svg.setAttribute('height', '24');
  svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor'); svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round'); svg.setAttribute('stroke-linejoin', 'round');
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
    try {
      if (appState.isListening) {
        const { stopVAD } = await import('../audio/vad.ts');
        await stopVAD();
      } else {
        const { startVAD } = await import('../audio/vad.ts');
        await startVAD();
      }
    } catch (err) { console.error('Mic toggle failed:', err); }
  });
  onStateChange((state) => {
    micBtn.classList.toggle('active', state.isListening);
    micBtn.classList.toggle('speaking', state.isSpeaking);
  });

  // Input bar
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
    const { addMessage, updateState, resetLatency } = await import('../state.ts');
    const { setMessageSentTimestamp } = await import('../orchestrator.ts');
    const { sendMessage } = await import('../net/websocket.ts');
    resetLatency();
    addMessage({ role: 'user', text });
    setMessageSentTimestamp(performance.now());
    await sendMessage(text);
    updateState({ isGenerating: true });
  };
  sendBtn.addEventListener('click', sendHandler);
  textInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendHandler(); });
  inputBar.appendChild(micBtn);
  inputBar.appendChild(textInput);
  inputBar.appendChild(sendBtn);
  mainContent.appendChild(inputBar);

  parent.appendChild(mainContent);

  return canvas;
}
