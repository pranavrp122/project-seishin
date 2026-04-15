import { MicVAD } from '@ricky0123/vad-web';
import { transcribe } from '../asr/whisper.ts';
import { sendMessage, sendStop } from '../net/websocket.ts';
import { updateState, addMessage, appState, resetLatency } from '../state.ts';
import { setMessageSentTimestamp } from '../orchestrator.ts';

let vad: MicVAD | null = null;

// Float32 to WAV blob conversion (16kHz mono PCM16)
function float32ToWav(samples: Float32Array, sampleRate: number): Blob {
  const numChannels = 1;
  const bitsPerSample = 16;
  const byteRate = sampleRate * numChannels * (bitsPerSample / 8);
  const blockAlign = numChannels * (bitsPerSample / 8);
  const dataSize = samples.length * (bitsPerSample / 8);
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  // RIFF header
  writeStr(view, 0, 'RIFF');
  view.setUint32(4, 36 + dataSize, true);
  writeStr(view, 8, 'WAVE');
  writeStr(view, 12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, byteRate, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, bitsPerSample, true);
  writeStr(view, 36, 'data');
  view.setUint32(40, dataSize, true);
  const off = 44;
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off + i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
  }
  return new Blob([buffer], { type: 'audio/wav' });
}

function writeStr(view: DataView, offset: number, str: string): void {
  for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
}

export async function startVAD(): Promise<void> {
  vad = await MicVAD.new({
    positiveSpeechThreshold: 0.8,
    negativeSpeechThreshold: 0.15,
    minSpeechMs: 90,
    preSpeechPadMs: 300,
    redemptionMs: 240,
    onSpeechStart: () => {
      updateState({ isSpeaking: true, interimTranscript: 'Listening...' });
      // If companion is generating, send barge-in stop
      if (appState.isGenerating) {
        sendStop();
      }
    },
    onSpeechEnd: async (audio: Float32Array) => {
      updateState({ isSpeaking: false });
      const asrStart = performance.now();
      resetLatency();
      try {
        const wavBlob = float32ToWav(audio, 16000);
        const text = await transcribe(wavBlob);
        const asrMs = performance.now() - asrStart;
        updateState({
          interimTranscript: '',
          latency: { ...appState.latency, asrMs },
        });
        if (text && text.length > 0) {
          addMessage({ role: 'user', text });
          // Set TTFT baseline timestamp before sending (enables latency tracking per D-14)
          setMessageSentTimestamp(performance.now());
          const sendStart = performance.now();
          await sendMessage(text);
          updateState({
            isGenerating: true,
            latency: {
              ...appState.latency,
              asrMs,
              networkSendMs: performance.now() - sendStart,
            },
          });
        }
      } catch (err) {
        console.error('ASR/send error:', err);
        updateState({ interimTranscript: '' });
      }
    },
  });
  await vad.start();
  updateState({ isListening: true });
}

export async function stopVAD(): Promise<void> {
  if (vad) { await vad.destroy(); vad = null; }
  updateState({ isListening: false, isSpeaking: false });
}
