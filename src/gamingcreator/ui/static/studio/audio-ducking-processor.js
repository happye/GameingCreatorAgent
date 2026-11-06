// Fixed Studio graph: two already-positioned source slots, music, narration.
// Keys are measured before user gains. All gain controls are AudioParams.
const definitions = [
  ['sourceGainDb', 0, -60, 0], ['musicGainDb', 0, -60, 0],
  ['narrationGainDb', 0, -60, 0], ['slotAGain', 1, 0, 1],
  ['slotBGain', 0, 0, 1], ['sourceDucking', 0, 0, 1],
  ['narrationDucking', 0, 0, 1], ['bedLimiter', 0, 0, 1],
  ['finalLimiter', 0, 0, 1],
];

class Detector {
  constructor() { this.level = 0; }
  gain(left, right) {
    // FFmpeg sidechaincompress default link=average, detection=rms.
    const amplitude = (Math.abs(left) + Math.abs(right)) / 2;
    const squared = amplitude * amplitude;
    const coefficient = Math.min(1, 4000 / (sampleRate * (squared > this.level ? 10 : 200)));
    this.level += (squared - this.level) * coefficient;
    return this.level > 0.015 ** 2
      ? Math.exp(Math.log(Math.sqrt(this.level) / 0.015) * (1 / 12 - 1)) : 1;
  }
}

class PeakLimiter {
  constructor() {
    this.delay = Math.max(1, Math.round(sampleRate * 0.005));
    this.left = new Float64Array(this.delay);
    this.right = new Float64Array(this.delay);
    this.index = 0;
    this.gain = 1;
    this.peaks = [];
    this.frame = 0;
    this.head = 0;
  }
  tick(left, right) {
    const oldLeft = this.left[this.index];
    const oldRight = this.right[this.index];
    this.left[this.index] = left;
    this.right[this.index] = right;
    this.index = (this.index + 1) % this.delay;
    const magnitude = Math.max(Math.abs(left), Math.abs(right));
    while (this.peaks.length > this.head && this.peaks.at(-1)[1] <= magnitude) this.peaks.pop();
    this.peaks.push([this.frame, magnitude]);
    while (this.peaks[this.head][0] < this.frame - this.delay) this.head++;
    const peak = this.peaks[this.head][1];
    this.frame++;
    if (this.head > 1024) { this.peaks = this.peaks.slice(this.head); this.head = 0; }
    const target = peak > 0.95 ? 0.95 / peak : 1;
    this.gain = target < this.gain ? target : Math.min(target, this.gain + 1 / (sampleRate * 0.05));
    return [oldLeft * this.gain, oldRight * this.gain];
  }
}

class StudioAudioProcessor extends AudioWorkletProcessor {
  static get parameterDescriptors() {
    return definitions.map(([name, defaultValue, minValue, maxValue]) =>
      ({name, defaultValue, minValue, maxValue, automationRate: 'a-rate'}));
  }
  constructor() {
    super();
    this.reset();
    this.port.onmessage = ({data}) => { if (data?.type === 'reset') this.reset(); };
  }
  reset() {
    this.sourceDetector = new Detector();
    this.narrationDetector = new Detector();
    this.bed = new PeakLimiter();
    this.final = new PeakLimiter();
  }
  process(inputs, outputs, parameters) {
    const output = outputs[0];
    const value = (name, i) => parameters[name][parameters[name].length === 1 ? 0 : i];
    const input = (slot, channel, i) => (inputs[slot]?.[channel] || inputs[slot]?.[0])?.[i] || 0;
    for (let i = 0; i < output[0].length; i++) {
      const raw = [0, 1].map(c => input(0, c, i) * value('slotAGain', i)
        + input(1, c, i) * value('slotBGain', i));
      const voice = [input(3, 0, i), input(3, 1, i)];
      const sourceKey = this.sourceDetector.gain(...raw);
      const narrationKey = this.narrationDetector.gain(...voice);
      const gain = name => 10 ** (value(name, i) / 20);
      const musicGain = gain('musicGainDb') * (value('sourceDucking', i) >= 0.5 ? sourceKey : 1);
      let bed = raw.map((sample, c) => sample * gain('sourceGainDb') + input(2, c, i) * musicGain);
      if (value('bedLimiter', i) >= 0.5) bed = this.bed.tick(...bed);
      let mixed = bed.map((sample, c) => sample * (value('narrationDucking', i) >= 0.5 ? narrationKey : 1)
        + voice[c] * gain('narrationGainDb'));
      if (value('finalLimiter', i) >= 0.5) mixed = this.final.tick(...mixed);
      output.forEach((channel, c) => { channel[i] = mixed[c % 2]; });
    }
    return true;
  }
}

registerProcessor('studio-audio-ducking', StudioAudioProcessor);
