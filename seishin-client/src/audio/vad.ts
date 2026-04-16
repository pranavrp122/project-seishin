import { MicVAD } from '@ricky0123/vad-web';
import { sendStop, sendSpeechStart, sendSpeechEnd, sendPCMChunk } from '../net/websocket.ts';
import { updateState, appState, resetLatency } from '../state.ts';
import { setMessageSentTimestamp } from '../orchestrator.ts';

let vad: MicVAD | null = null;
let micStream: MediaStream | null = null;
let micAudioCtx: AudioContext | null = null;
let micAnalyser: AnalyserNode | null = null;
let micProcessor: ScriptProcessorNode | null = null;
let isStreamingAudio = false;

// Ring buffer: 500ms at 16kHz = 8000 samples of Int16
const RING_SIZE = 8000;
const ringBuf = new Int16Array(RING_SIZE);
let ringPos = 0;
let ringWrapped = false;

function downsample(input: Float32Array, fromRate: number, toRate: number): Float32Array {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const len = Math.round(input.length / ratio);
  const out = new Float32Array(len);
  for (let i = 0; i < len; i++) out[i] = input[Math.round(i * ratio)];
  return out;
}

function float32ToInt16(samples: Float32Array): Int16Array {
  const out = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return out;
}

function writeRing(pcm: Int16Array): void {
  for (let i = 0; i < pcm.length; i++) {
    ringBuf[ringPos] = pcm[i];
    ringPos = (ringPos + 1) % RING_SIZE;
    if (ringPos === 0) ringWrapped = true;
  }
}

function flushRing(): ArrayBuffer {
  const count = ringWrapped ? RING_SIZE : ringPos;
  const start = ringWrapped ? ringPos : 0;
  const out = new Int16Array(count);
  for (let i = 0; i < count; i++) out[i] = ringBuf[(start + i) % RING_SIZE];
  ringPos = 0;
  ringWrapped = false;
  return out.buffer;
}

export function getMicAnalyser(): AnalyserNode | null {
  return micAnalyser;
}

export async function startVAD(): Promise<void> {
  // Set up mic analyser for input waveform visualization
  micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  micAudioCtx = new AudioContext();
  const source = micAudioCtx.createMediaStreamSource(micStream);
  micAnalyser = micAudioCtx.createAnalyser();
  micAnalyser.fftSize = 256;
  source.connect(micAnalyser);

  // Continuous PCM capture: downsample to 16kHz, write to ring buffer, stream when speaking
  micProcessor = micAudioCtx.createScriptProcessor(4096, 1, 1);
  micProcessor.onaudioprocess = (e) => {
    const raw = e.inputBuffer.getChannelData(0);
    const pcm16 = float32ToInt16(downsample(raw, micAudioCtx!.sampleRate, 16000));
    writeRing(pcm16);
    if (isStreamingAudio) {
      sendPCMChunk(pcm16.buffer);
    }
  };
  source.connect(micProcessor);
  micProcessor.connect(micAudioCtx.destination); // output is silent (zeros)

  vad = await MicVAD.new({
    baseAssetPath: '/',
    onnxWASMBasePath: '/',
    positiveSpeechThreshold: 0.6,
    negativeSpeechThreshold: 0.10,
    minSpeechMs: 60,
    preSpeechPadMs: 400,
    redemptionMs: 400,
    onSpeechStart: () => {
      updateState({ isSpeaking: true, interimTranscript: 'Listening...' });
      if (appState.isGenerating) {
        sendStop();
      } else {
        // Flush pre-speech ring buffer and start live streaming
        sendSpeechStart();
        const catchUp = flushRing();
        if (catchUp.byteLength > 0) sendPCMChunk(catchUp);
        isStreamingAudio = true;
      }
    },
    onSpeechEnd: async (_audio: Float32Array) => {
      updateState({ isSpeaking: false });
      isStreamingAudio = false;
      if (!appState.isGenerating) {
        resetLatency();
        setMessageSentTimestamp(performance.now());
        updateState({ interimTranscript: 'Transcribing...' });
        sendSpeechEnd();
      }
    },
  });
  await vad.start();
  updateState({ isListening: true });
}

export async function stopVAD(): Promise<void> {
  isStreamingAudio = false;
  if (vad) { await vad.destroy(); vad = null; }
  if (micProcessor) { micProcessor.disconnect(); micProcessor = null; }
  if (micStream) {
    micStream.getTracks().forEach(t => t.stop());
    micStream = null;
  }
  if (micAudioCtx) {
    await micAudioCtx.close();
    micAudioCtx = null;
  }
  micAnalyser = null;
  updateState({ isListening: false, isSpeaking: false });
}
