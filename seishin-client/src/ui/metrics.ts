import { onStateChange, appState } from '../state.ts';
import { LatencyMetrics } from '../types.ts';

let metricsEl: HTMLDivElement | null = null;
let asrVal: HTMLSpanElement | null = null;
let ttftVal: HTMLSpanElement | null = null;
let ttsVal: HTMLSpanElement | null = null;
let totalVal: HTMLSpanElement | null = null;

/** Format a latency value for display */
function fmt(ms: number | null): string {
  if (ms === null) return '--';
  return `${Math.round(ms)}ms`;
}

/** Render the latency metrics panel per D-14, D-15 (always visible) */
export function renderMetrics(parent: HTMLElement): void {
  metricsEl = document.createElement('div');
  metricsEl.id = 'metrics-panel';
  metricsEl.className = 'metrics-panel';

  const rows: Array<{ label: string; ref: 'asr' | 'ttft' | 'tts' | 'total' }> = [
    { label: 'ASR', ref: 'asr' },
    { label: 'TTFT', ref: 'ttft' },
    { label: 'TTS', ref: 'tts' },
    { label: 'Total', ref: 'total' },
  ];

  for (const row of rows) {
    const item = document.createElement('div');
    item.className = 'metric-item';

    const labelSpan = document.createElement('span');
    labelSpan.className = 'metric-label';
    labelSpan.textContent = row.label;
    item.appendChild(labelSpan);

    const valSpan = document.createElement('span');
    valSpan.className = 'metric-value';
    valSpan.textContent = '--';
    item.appendChild(valSpan);

    metricsEl.appendChild(item);

    // Store references for direct updates
    if (row.ref === 'asr') asrVal = valSpan;
    else if (row.ref === 'ttft') ttftVal = valSpan;
    else if (row.ref === 'tts') ttsVal = valSpan;
    else if (row.ref === 'total') totalVal = valSpan;
  }

  parent.appendChild(metricsEl);

  onStateChange((state) => updateMetricsDisplay(state.latency));
  updateMetricsDisplay(appState.latency);
}

function updateMetricsDisplay(latency: LatencyMetrics): void {
  if (asrVal) asrVal.textContent = fmt(latency.asrMs);
  if (ttftVal) ttftVal.textContent = fmt(latency.ttftMs);
  if (ttsVal) ttsVal.textContent = fmt(latency.ttsMs);
  if (totalVal) totalVal.textContent = fmt(latency.totalMs);
}
