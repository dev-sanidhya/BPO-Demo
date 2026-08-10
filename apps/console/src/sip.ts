import JsSIP from "jssip";

export type SipStatus = "disabled" | "connecting" | "registered" | "calling" | "connected" | "failed";

export interface SipEvents {
  onStatus: (status: SipStatus, detail?: string) => void;
  onIncoming: (remote: string) => void;
  onEnded: () => void;
  onMedia: (remote: MediaStream, local: MediaStream) => void;
}

export class SipPhone {
  private ua: any = null;
  private session: any = null;
  private events: SipEvents;

  constructor(events: SipEvents) {
    this.events = events;
  }

  start() {
    const config = window.platformRuntime?.sip;
    if (!config?.enabled) {
      this.events.onStatus("disabled", "Demo media mode");
      return;
    }
    this.events.onStatus("connecting", `Registering ${config.extension}`);
    try {
      const socket = new JsSIP.WebSocketInterface(config.wsUrl);
      this.ua = new JsSIP.UA({ sockets: [socket], uri: `sip:${config.extension}@${config.host}`, password: config.password, register: true });
      this.ua.on("registered", () => this.events.onStatus("registered", `SIP ${config.extension}`));
      this.ua.on("registrationFailed", (event: any) => this.events.onStatus("failed", event.cause || "Registration failed"));
      this.ua.on("disconnected", () => this.events.onStatus("failed", "Asterisk disconnected"));
      this.ua.on("newRTCSession", ({ session }: any) => this.bindSession(session));
      this.ua.start();
    } catch (error) {
      this.events.onStatus("failed", error instanceof Error ? error.message : "SIP initialization failed");
    }
  }

  stop() {
    if (this.session && !this.session.isEnded?.()) this.session.terminate();
    this.ua?.stop();
    this.session = null;
    this.ua = null;
  }

  call(target: string) {
    const config = window.platformRuntime?.sip;
    if (!this.ua || !config || !/^\d{3,8}$/.test(target)) throw new Error("Live SIP requires a registered phone and an internal extension");
    this.events.onStatus("calling", `Calling ${target}`);
    this.session = this.ua.call(`sip:${target}@${config.host}`, { mediaConstraints: { audio: true, video: false } });
  }

  answer() {
    if (!this.session || this.session.direction !== "incoming") throw new Error("No incoming SIP call is waiting");
    this.session.answer({ mediaConstraints: { audio: true, video: false } });
  }

  reject() {
    if (this.session && !this.session.isEnded?.()) this.session.terminate({ status_code: 486, reason_phrase: "Busy Here" });
  }

  mute(value: boolean) {
    if (!this.session) return;
    value ? this.session.mute({ audio: true }) : this.session.unmute({ audio: true });
  }

  hold(value: boolean) {
    if (!this.session) return;
    value ? this.session.hold() : this.session.unhold();
  }

  transfer(target: string) {
    const config = window.platformRuntime?.sip;
    if (this.session && config && /^\d{3,8}$/.test(target)) this.session.refer(`sip:${target}@${config.host}`);
  }

  hangup() {
    if (this.session && !this.session.isEnded?.()) this.session.terminate();
  }

  private bindSession(session: any) {
    this.session = session;
    if (session.direction === "incoming") {
      const remote = String(session.remote_identity?.uri?.user || "unknown");
      this.events.onStatus("calling", `Incoming SIP call from ${remote}`);
      this.events.onIncoming(remote);
    }
    const ended = (resetStatus = true) => {
      this.session = null;
      if (resetStatus) this.events.onStatus("registered", `SIP ${window.platformRuntime?.sip?.extension || ""}`);
      this.events.onEnded();
    };
    session.on("confirmed", () => this.events.onStatus("connected", "Two-party media"));
    session.on("ended", ended);
    session.on("failed", (event: any) => {
      this.events.onStatus("failed", event.cause || "Call failed");
      ended(false);
    });
    const bindPeerConnection = () => session.connection?.addEventListener("track", (event: RTCTrackEvent) => {
        const remote = event.streams[0] || new MediaStream([event.track]);
        const localTracks = session.connection.getSenders().map((sender: RTCRtpSender) => sender.track).filter(Boolean) as MediaStreamTrack[];
        this.events.onMedia(remote, new MediaStream(localTracks));
      }, { once: true });
    if (session.connection) bindPeerConnection();
    else session.on("peerconnection", bindPeerConnection);
  }
}
