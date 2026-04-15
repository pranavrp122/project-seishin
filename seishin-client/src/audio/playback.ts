let audioCtx: AudioContext | null = null;
let workletNode: AudioWorkletNode | null = null;
let analyserNode: AnalyserNode | null = null;
let currentPosition = { readIdx: 0, writeIdx: 0 };

export async function initPlayback(): Promise<AudioWorkletNode> {
  // 44100Hz to match Fish Speech PCM output -- Pitfall 5
  audioCtx = new AudioContext({ sampleRate: 44100 });
  await audioCtx.audioWorklet.addModule('/playback-processor.js');
  workletNode = new AudioWorkletNode(audioCtx, 'pcm-playback-processor');

  // AnalyserNode for waveform visualization per D-12
  analyserNode = audioCtx.createAnalyser();
  analyserNode.fftSize = 256;
  workletNode.connect(analyserNode);
  analyserNode.connect(audioCtx.destination);

  // Track playback position for text-audio sync per D-11
  workletNode.port.onmessage = (e: MessageEvent) => {
    if (e.data.type === 'position') {
      currentPosition = { readIdx: e.data.readIdx, writeIdx: e.data.writeIdx };
    }
  };

  return workletNode;
}

// Convert PCM int16 bytes from WebSocket to Float32 for AudioWorklet
function pcmInt16ToFloat32(pcmBytes: Uint8Array): Float32Array {
  const int16 = new Int16Array(pcmBytes.buffer, pcmBytes.byteOffset, pcmBytes.byteLength / 2);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768;
  }
  return float32;
}

export function enqueuePCM(pcmBytes: Uint8Array): void {
  if (!workletNode) return;
  const samples = pcmInt16ToFloat32(pcmBytes);
  workletNode.port.postMessage({ type: 'audio', samples });
}

export function clearPlayback(): void {
  if (workletNode) {
    workletNode.port.postMessage({ type: 'clear' });
  }
  currentPosition = { readIdx: 0, writeIdx: 0 };
}

// Returns current playback position (sample index) for text-audio sync
export function getPlaybackPosition(): { readIdx: number; writeIdx: number } {
  return currentPosition;
}

export function getAnalyserNode(): AnalyserNode | null {
  return analyserNode;
}

export function getAudioContext(): AudioContext | null {
  return audioCtx;
}

// Resume AudioContext (needed after user gesture on some browsers)
export async function resumePlayback(): Promise<void> {
  if (audioCtx && audioCtx.state === 'suspended') {
    await audioCtx.resume();
  }
}
