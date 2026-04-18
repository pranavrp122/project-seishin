import { renderChat } from './chat.ts';
import { renderReportLog } from './report-log.ts';
import { renderMetrics } from './metrics.ts';

/**
 * Text-mode layout — no waveform, no mic button.
 *
 * +-------+-------------------------------+
 * | [Chat]|  main view (chat OR log)      |
 * | [Log] |                               |
 * |       |-------------------------------|
 * |       |  text input bar               |
 * +-------+-------------------------------+
 */
export function renderLayout(parent: HTMLElement): void {
  while (parent.firstChild) parent.removeChild(parent.firstChild);
  parent.style.flexDirection = 'row';

  // ── Side nav ───────────────────────────────────────────────────────────
  const sideNav = document.createElement('div');
  sideNav.id = 'side-nav';
  sideNav.className = 'side-nav';

  const toggleBtn = document.createElement('button');
  toggleBtn.className = 'side-nav-toggle';
  toggleBtn.title = 'Toggle sidebar';
  toggleBtn.textContent = '☰';
  toggleBtn.addEventListener('click', () => sideNav.classList.toggle('open'));
  sideNav.appendChild(toggleBtn);

  const navItems = [
    { id: 'nav-chat', label: 'Chat', view: 'chat' },
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

  // Top bar with metrics (TTFT etc)
  const topBar = document.createElement('div');
  topBar.className = 'top-bar';
  const metricsContainer = document.createElement('div');
  metricsContainer.className = 'metrics-container';
  renderMetrics(metricsContainer);
  topBar.appendChild(metricsContainer);
  mainContent.appendChild(topBar);

  // View area
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

  // Nav switching
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

  // ── Text input bar ─────────────────────────────────────────────────────
  const inputBar = document.createElement('div');
  inputBar.className = 'input-bar';

  const textInput = document.createElement('input');
  textInput.type = 'text';
  textInput.className = 'text-input';
  textInput.placeholder = 'Ask anything...';
  textInput.autofocus = true;

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
    updateState({ isGenerating: true });
    await sendMessage(text);
  };

  sendBtn.addEventListener('click', sendHandler);
  textInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendHandler(); });

  inputBar.appendChild(textInput);
  inputBar.appendChild(sendBtn);
  mainContent.appendChild(inputBar);

  parent.appendChild(mainContent);
}
