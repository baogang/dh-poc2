class Capture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = new Int16Array(320); this.n = 0; }
  process(inputs) {
    const a = inputs[0]?.[0];
    if (a) for (const v of a) {
      this.buf[this.n++] = Math.round(Math.max(-1, Math.min(1, v))*32767);
      if (this.n === 320) { this.port.postMessage(this.buf.slice().buffer); this.n = 0; }
    }
    return true;
  }
}
registerProcessor('capture', Capture);
