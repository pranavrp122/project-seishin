// TypeScript reference for public/playback-processor.js
// The actual AudioWorklet module is the plain JS file in public/.
// This file exists for type-checking and documentation only.

class PCMPlaybackProcessor extends AudioWorkletProcessor {
  private buffer: Float32Array;
  private writeIdx: number;
  private readIdx: number;
  private capacity: number;

  constructor() {
    super();
    // 5 seconds buffer at 44.1kHz -- enough for streaming without underrun
    this.capacity = 44100 * 5;
    this.buffer = new Float32Array(this.capacity);
    this.writeIdx = 0;
    this.readIdx = 0;

    this.port.onmessage = (e: MessageEvent) => {
      if (e.data.type === 'audio') {
        this.enqueue(e.data.samples as Float32Array);
      } else if (e.data.type === 'clear') {
        this.writeIdx = 0;
        this.readIdx = 0;
      } else if (e.data.type === 'query-position') {
        this.port.postMessage({ type: 'position', readIdx: this.readIdx, writeIdx: this.writeIdx });
      }
    };
  }

  private enqueue(samples: Float32Array): void {
    for (let i = 0; i < samples.length; i++) {
      this.buffer[this.writeIdx % this.capacity] = samples[i];
      this.writeIdx++;
    }
    // Notify main thread of buffer fill for text-audio sync
    this.port.postMessage({ type: 'position', readIdx: this.readIdx, writeIdx: this.writeIdx });
  }

  process(_inputs: Float32Array[][], outputs: Float32Array[][]): boolean {
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
