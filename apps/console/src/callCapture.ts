export class CallCapture {
  private context: AudioContext;
  private destination: MediaStreamAudioDestinationNode;
  private fullRecorder: MediaRecorder;
  private fullChunks: Blob[] = [];
  private segmentRecorder: MediaRecorder | null = null;
  private segmentTimer: number | null = null;
  private active = true;
  private elapsedMs = 0;
  private startedAt = performance.now();
  private onChunk: (blob: Blob, startMs: number) => Promise<void>;

  constructor(remote: MediaStream, local: MediaStream, onChunk: (blob: Blob, startMs: number) => Promise<void>) {
    this.onChunk = onChunk;
    this.context = new AudioContext();
    this.destination = this.context.createMediaStreamDestination();
    if (remote.getAudioTracks().length) this.context.createMediaStreamSource(remote).connect(this.destination);
    if (local.getAudioTracks().length) this.context.createMediaStreamSource(local).connect(this.destination);
    this.fullRecorder = new MediaRecorder(this.destination.stream, { mimeType: "audio/webm;codecs=opus" });
    this.fullRecorder.ondataavailable = (event) => { if (event.data.size) this.fullChunks.push(event.data); };
    this.fullRecorder.start();
    this.startSegment();
  }

  private startSegment() {
    if (!this.active) return;
    const startMs = this.elapsedMs;
    const started = performance.now();
    const recorder = new MediaRecorder(this.destination.stream, { mimeType: "audio/webm;codecs=opus" });
    this.segmentRecorder = recorder;
    const chunks: Blob[] = [];
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      const duration = Math.max(roundToSecond(performance.now() - started), 1_000);
      this.elapsedMs = startMs + duration;
      const blob = new Blob(chunks, { type: "audio/webm" });
      if (blob.size && this.active) void this.onChunk(blob, startMs);
      if (this.active) this.startSegment();
    };
    recorder.start();
    this.segmentTimer = window.setTimeout(() => { if (recorder.state === "recording") recorder.stop(); }, 15_000);
  }

  async stop(): Promise<{ blob: Blob; durationMs: number }> {
    this.active = false;
    if (this.segmentTimer !== null) window.clearTimeout(this.segmentTimer);
    if (this.segmentRecorder?.state === "recording") this.segmentRecorder.stop();
    const blob = await new Promise<Blob>((resolve) => {
      this.fullRecorder.onstop = () => resolve(new Blob(this.fullChunks, { type: "audio/webm" }));
      if (this.fullRecorder.state === "recording") this.fullRecorder.stop();
      else resolve(new Blob(this.fullChunks, { type: "audio/webm" }));
    });
    const durationMs = Math.max(roundToSecond(performance.now() - this.startedAt), 1_000);
    await this.context.close();
    return { blob, durationMs };
  }
}

function roundToSecond(value: number) {
  return Math.round(value / 1000) * 1000;
}
