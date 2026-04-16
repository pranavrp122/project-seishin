import { getAnalyserNode } from './playback';
import { getMicAnalyser } from './vad';
import { appState } from '../state';

let canvas: HTMLCanvasElement | null = null;
let animFrameId: number | null = null;

export function initWaveform(targetCanvas: HTMLCanvasElement): void {
  canvas = targetCanvas;
  startDrawLoop();
}

function startDrawLoop(): void {
  if (animFrameId !== null) return;

  function draw(): void {
    animFrameId = requestAnimationFrame(draw);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Show mic input when speaking, companion playback otherwise
    const micAnalyser = getMicAnalyser();
    const playbackAnalyser = getAnalyserNode();

    let analyser: AnalyserNode | null = null;
    let color = '#6366f1';

    if (appState.isSpeaking && micAnalyser) {
      analyser = micAnalyser;
      color = '#22c55e'; // Green for user voice
    } else if (playbackAnalyser) {
      analyser = playbackAnalyser;
      color = '#6366f1'; // Indigo for companion
    }

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (!analyser) return;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    const barWidth = canvas.width / dataArray.length;
    const midY = canvas.height / 2;

    for (let i = 0; i < dataArray.length; i++) {
      const barHeight = (dataArray[i] / 255) * midY;
      // Draw bars symmetrically from center -- voice waveform bar style per D-12
      ctx.fillStyle = color;
      ctx.fillRect(i * barWidth, midY - barHeight, barWidth - 1, barHeight);
      ctx.fillRect(i * barWidth, midY, barWidth - 1, barHeight);
    }
  }

  draw();
}

export function stopWaveform(): void {
  if (animFrameId !== null) {
    cancelAnimationFrame(animFrameId);
    animFrameId = null;
  }
}

export function getWaveformCanvas(): HTMLCanvasElement | null {
  return canvas;
}
