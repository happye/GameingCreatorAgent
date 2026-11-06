// One graph per mounted editor. Rendered result videos never enter this graph.
export class AudioPreviewGraph {
    constructor(elements, report) {
        this.elements = elements;
        this.report = report;
        this.closed = false;
        this.active = false;
        this.settings = {};
        this.weights = [0, 0];
        this.context = new AudioContext();
        this.gate = this.context.createGain();
        this.gate.gain.value = 0;
        this.gate.connect(this.context.destination);
        this.sources = elements.map(element => {
            element.volume = 1;
            element.studioAudioGraph = this;
            return this.context.createMediaElementSource(element);
        });
        this.gesture = () => { if (!this.closed) void this.context.resume().catch(error => this.fail(error)); };
        document.addEventListener('pointerdown', this.gesture, true);
        document.addEventListener('keydown', this.gesture, true);
        this.ready = this.initialize();
    }
    async initialize() {
        try {
            await this.context.audioWorklet.addModule(new URL('./audio-ducking-processor.js', import.meta.url));
            if (this.closed) return;
            this.node = new AudioWorkletNode(this.context, 'studio-audio-ducking', {
                numberOfInputs: 4, numberOfOutputs: 1, outputChannelCount: [2],
            });
            this.node.onprocessorerror = () => this.fail(new Error('音频处理器停止'));
            this.sources.forEach((source, index) => source.connect(this.node, 0, index));
            this.node.connect(this.gate);
            this.configure(this.settings);
            this.weights.forEach((gain, index) => this.slot(this.elements[index], gain));
            this.enable(this.active);
        } catch (error) { this.fail(error); }
    }
    fail(error) {
        this.failed = true;
        this.enable(false);
        this.elements.forEach(element => element.pause());
        this.report(`即时音频试听不可用：${error.message}。请导出成片试听。`);
    }
    configure(audio) {
        const identity = JSON.stringify([audio.mix?.bgm?.trackId, audio.narration?.assetJobId, audio.narration?.startFrame]);
        if (this.identity !== identity) { this.reset(); this.identity = identity; }
        this.settings = audio;
        const mix = audio.mix || {}, narration = audio.narration;
        const values = {
            sourceGainDb: mix.sourceGainDb || 0, musicGainDb: mix.bgm?.gainDb || 0,
            narrationGainDb: narration?.gainDb || 0,
            sourceDucking: mix.ducking === 'source-v1' ? 1 : 0,
            narrationDucking: narration?.ducking === 'narration-v1' ? 1 : 0,
            bedLimiter: mix.bgm ? 1 : 0, finalLimiter: narration ? 1 : 0,
        };
        Object.entries(values).forEach(([name, value]) => {
            this.node?.parameters.get(name).setValueAtTime(value, this.context.currentTime);
        });
    }
    slot(element, gain) {
        const index = this.elements.indexOf(element);
        if (index < 0 || index > 1) return;
        this.weights[index] = gain;
        element.volume = 1;
        this.node?.parameters.get(index ? 'slotBGain' : 'slotAGain').setValueAtTime(gain, this.context.currentTime);
    }
    enable(active) {
        this.active = active && !this.failed && !this.closed;
        this.gate.gain.setValueAtTime(this.active && this.node ? 1 : 0, this.context.currentTime);
    }
    reset() {
        this.enable(false);
        this.node?.port.postMessage({type: 'reset'});
        this.elements.slice(2).forEach(element => element.pause());
    }
    dispose() {
        this.reset();
        this.closed = true;
        document.removeEventListener('pointerdown', this.gesture, true);
        document.removeEventListener('keydown', this.gesture, true);
        this.elements.forEach(element => { element.pause(); delete element.studioAudioGraph; });
        this.sources.forEach(source => source.disconnect());
        this.node?.disconnect(); this.gate.disconnect();
        void this.context.close();
    }
}
