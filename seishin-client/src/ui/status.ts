import { onStateChange } from '../state.ts';
import { ConnectionStatus } from '../types.ts';

const STATUS_COLORS: Record<ConnectionStatus, string> = {
  connected: '#4ade80',
  degraded: '#facc15',
  disconnected: '#f87171',
  connecting: '#60a5fa',
  reconnecting: '#60a5fa',
};

const STATUS_LABELS: Record<ConnectionStatus, string> = {
  connected: 'Connected',
  degraded: 'Degraded',
  disconnected: 'Disconnected',
  connecting: 'Connecting',
  reconnecting: 'Reconnecting',
};

let dot: HTMLSpanElement | null = null;
let label: HTMLSpanElement | null = null;

export function renderStatus(parent: HTMLElement): void {
  const pill = document.createElement('div');
  pill.id = 'status-pill';
  pill.style.cssText = `
    position: fixed;
    top: 12px;
    right: 12px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 12px;
    background: #1a1a24;
    border: 1px solid #2a2a3a;
    font-size: 12px;
    z-index: 100;
  `;

  dot = document.createElement('span');
  dot.style.cssText = `
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: ${STATUS_COLORS.disconnected};
    display: inline-block;
    transition: background 0.3s;
  `;
  pill.appendChild(dot);

  label = document.createElement('span');
  label.textContent = STATUS_LABELS.disconnected;
  label.style.cssText = 'color: #8888a0; transition: color 0.3s;';
  pill.appendChild(label);

  parent.appendChild(pill);

  onStateChange((state) => {
    if (!dot || !label) return;

    const color = STATUS_COLORS[state.connection];
    dot.style.background = color;
    label.textContent = STATUS_LABELS[state.connection];

    // Pulse animation for connecting/reconnecting states
    if (state.connection === 'connecting' || state.connection === 'reconnecting') {
      dot.style.animation = 'status-pulse 1s ease-in-out infinite';
    } else {
      dot.style.animation = 'none';
    }
  });

  // Inject keyframes for pulse animation
  if (!document.getElementById('status-pulse-style')) {
    const style = document.createElement('style');
    style.id = 'status-pulse-style';
    style.textContent = `
      @keyframes status-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
      }
    `;
    document.head.appendChild(style);
  }
}
