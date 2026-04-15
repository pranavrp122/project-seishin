import { renderChat } from './chat.ts';
import { renderMetrics } from './metrics.ts';
import { initWaveform } from '../audio/waveform.ts';

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

  return canvas;
}
