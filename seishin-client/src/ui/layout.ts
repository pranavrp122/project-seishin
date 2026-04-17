import { renderChat } from './chat.ts';
import { renderMetrics } from './metrics.ts';
import { renderReportLog } from './report-log.ts';
import { initWaveform } from '../audio/waveform.ts';
import { onStateChange } from '../state.ts';

/**
 * Layout:
 *
 * +--[≡]--+-------------------------------+
 * |       |  top-bar (metrics)            |
 * | [Chat]|-------------------------------|
 * | [Log] |  main view (chat OR log)      |
 * |       |  switches on nav click        |
 * |       |-------------------------------|
 * |       |  waveform                     |
 * |       |-------------------------------|
 * |       |  input bar (mic + text)       |
 * +-------+-------------------------------+
 *
 * Sidebar is a collapsible nav drawer — clicking an item swaps the main view.
 */
export function renderLayout(parent: HTMLElement): HTMLCanvasElement {
  while (parent.firstChild) parent.removeChild(parent.firstChild);
  parent.style.flexDirection = 'row';

  // ── Side nav ───────────────────────────────────────────────────────────
  const sideNav = document.createElement('div');
  sideNav.id = 'side-nav';
  sideNav.className = 'side-nav';

  // Toggle button (top of nav)
  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'side-nav-toggle';
  toggleBtn.title = 'Toggle sidebar';
  toggleBtn.textContent = '☰';
  toggleBtn.addEventListener('click', () => {
    sideNav.classList.toggle('open');
  });
  sideNav.appendChild(toggleBtn);

  // Nav items
  const navItems = [
    { id: 'nav-chat', label: 'Chatbot', view: 'chat' },
    { id: 'nav-log',  label: 'Report Log', view: 'log' },
  ];

  const navEls: HTMLButtonElement[] = [];
  for (const item of navItems) {
    const btn = document.createElement('button');
    btn.id = item.id;
    btn.className = 'side-nav-item' + (item.view === 'chat' ? ' active' : '');
    btn.textContent = item.label;
    btn.dataset.view = item.view;
    navEls.push(btn);
    sideNav.appendChild(btn);
  }

  parent.appendChild(sideNav);

  // ── Main content ───────────────────────────────────────────────────────
  const mainContent = document.createElement('div');
  mainContent.id = 'main-content';
  mainContent.className = 'main-content';

  // Top bar
  const topBar = document.createElement('div');
  topBar.className = 'top-bar';
  const metricsContainer = document.createElement('div');
  metricsContainer.className = 'metrics-container';
  renderMetrics(metricsContainer);
  topBar.appendChild(metricsContainer);
  mainContent.appendChild(topBar);

  // View area — swaps between chat and log
  const viewArea = document.createElement('div');
  viewArea.id = 'view-area';
  viewArea.className = 'view-area';

  const chatView = document.createElement('div');
  chatView.id = 'view-chat';
  chatView.className = 'view active';
  renderChat(chatView);
  viewArea.appendChild(chatView);

  const logView = document.createElement('div');
  logView.id = 'view-log';
  logView.className = 'view';
  renderReportLog(logView);
  viewArea.appendChild(logView);

  mainContent.appendChild(viewArea);

  // Wire nav item clicks → swap views
  navEls.forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.dataset.view;
      navEls.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      [chatView, logView].forEach(v => {
        v.classList.toggle('active', v.id === `view-${target}`);
      });
    });
  });

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
  onStateChange(state => {
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
  textInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendHandler(); });
  inputBar.appendChild(micBtn);
  inputBar.appendChild(textInput);
  inputBar.appendChild(sendBtn);
  mainContent.appendChild(inputBar);

  parent.appendChild(mainContent);
  return canvas;
}
