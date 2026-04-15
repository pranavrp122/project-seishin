import { getAnalyserNode } from './playback';

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
    const analyser = getAnalyserNode();
    if (!analyser || !canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const barWidth = canvas.width / dataArray.length;
    const midY = canvas.height / 2;

    for (let i = 0; i < dataArray.length; i++) {
      const barHeight = (dataArray[i] / 255) * midY;
      // Draw bars symmetrically from center -- voice waveform bar style per D-12
      ctx.fillStyle = '#6366f1'; // Indigo-500
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
