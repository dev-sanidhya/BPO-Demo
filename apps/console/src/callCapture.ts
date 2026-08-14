type Speaker = "agent" | "customer";

class SpeakerCapture {
  private active = true;
  private elapsedMs = 0;
  private recorder: MediaRecorder | null = null;
  private timer: number | null = null;
  private pending: Promise<void>[] = [];
  private failure: unknown = null;

  constructor(
    private stream: MediaStream,
    private speaker: Speaker,
    private onChunk: (blob: Blob, startMs: number, speaker: Speaker) => Promise<void>,
  ) {
    this.startSegment();
  }

  private startSegment() {
    if (!this.active || !this.stream.getAudioTracks().length) return;
    const startMs = this.elapsedMs;
    const startedAt = performance.now();
    const recorder = new MediaRecorder(this.stream, { mimeType: "audio/webm;codecs=opus" });
    const chunks: Blob[] = [];
    this.recorder = recorder;
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
    recorder.onstop = () => {
      const durationMs = Math.max(roundToSecond(performance.now() - startedAt), 1_000);
      this.elapsedMs = startMs + durationMs;
      const blob = new Blob(chunks, { type: "audio/webm" });
      if (blob.size) {
        const upload = this.onChunk(blob, startMs, this.speaker).catch((error) => { this.failure = error; });
        this.pending.push(upload);
      }
      if (this.active) this.startSegment();
    };
    recorder.start();
    // Keep the first live transcript and guidance update visible during a natural
    // customer exchange rather than waiting until the call is nearly over.
    this.timer = window.setTimeout(() => { if (recorder.state === "recording") recorder.stop(); }, 6_000);
  }

  async stop() {
    this.active = false;
    if (this.timer !== null) window.clearTimeout(this.timer);
    const stopped = new Promise<void>((resolve) => {
      const recorder = this.recorder;
      if (!recorder || recorder.state !== "recording") { resolve(); return; }
      const previous = recorder.onstop;
      recorder.onstop = (event) => { previous?.call(recorder, event); resolve(); };
      recorder.stop();
    });
    await stopped;
    await Promise.all(this.pending);
    if (this.failure) throw this.failure;
  }
}

export class CallCapture {
  private context: AudioContext;
  private destination: MediaStreamAudioDestinationNode;
  private fullRecorder: MediaRecorder;
  private fullChunks: Blob[] = [];
  private speakerCaptures: SpeakerCapture[];
  private startedAt = performance.now();

  constructor(remote: MediaStream, local: MediaStream, onChunk: (blob: Blob, startMs: number, speaker: Speaker) => Promise<void>) {
    this.context = new AudioContext();
    this.destination = this.context.createMediaStreamDestination();
    if (remote.getAudioTracks().length) this.context.createMediaStreamSource(remote).connect(this.destination);
    if (local.getAudioTracks().length) this.context.createMediaStreamSource(local).connect(this.destination);
    this.fullRecorder = new MediaRecorder(this.destination.stream, { mimeType: "audio/webm;codecs=opus" });
    this.fullRecorder.ondataavailable = (event) => { if (event.data.size) this.fullChunks.push(event.data); };
    this.fullRecorder.start();
    this.speakerCaptures = [
      new SpeakerCapture(remote, "customer", onChunk),
      new SpeakerCapture(local, "agent", onChunk),
    ];
  }

  async stop(): Promise<{ blob: Blob; durationMs: number }> {
    await Promise.all(this.speakerCaptures.map((capture) => capture.stop()));
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
