// AudioWorklet processor for streaming PCM playback with ring buffer.
// This file runs in the AudioWorklet thread -- no imports allowed.
class PCMPlaybackProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 30 seconds buffer at 44.1kHz -- Fish Speech generates ~3x real-time,
    // so a 10s response fills 10s of audio in ~3.3s while only 3.3s plays back.
    // 30s capacity prevents writeIdx from lapping readIdx on long responses.
    this.capacity = 44100 * 30;
    this.buffer = new Float32Array(this.capacity);
    this.writeIdx = 0;
    this.readIdx = 0;

    this.port.onmessage = (e) => {
      if (e.data.type === 'audio') {
        this.enqueue(e.data.samples);
      } else if (e.data.type === 'clear') {
        this.writeIdx = 0;
        this.readIdx = 0;
      } else if (e.data.type === 'query-position') {
        this.port.postMessage({ type: 'position', readIdx: this.readIdx, writeIdx: this.writeIdx });
      }
    };
  }

  enqueue(samples) {
    const buffered = this.writeIdx - this.readIdx;
    const available = this.capacity - buffered;
    // Drop samples that would overwrite unplayed audio
    const count = Math.min(samples.length, available);
    for (let i = 0; i < count; i++) {
      this.buffer[this.writeIdx % this.capacity] = samples[i];
      this.writeIdx++;
    }
    // Notify main thread of buffer fill for text-audio sync
    this.port.postMessage({ type: 'position', readIdx: this.readIdx, writeIdx: this.writeIdx });
  }

  process(_inputs, outputs) {
    const output = outputs[0][0];
    for (let i = 0; i < output.length; i++) {
      if (this.readIdx < this.writeIdx) {
        output[i] = this.buffer[this.readIdx % this.capacity];
        this.readIdx++;
      } else {
        output[i] = 0; // Silence when buffer is empty
      }
    }
    return true; // Keep processor alive
  }
}

registerProcessor('pcm-playback-processor', PCMPlaybackProcessor);
