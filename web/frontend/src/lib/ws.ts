// WebSocket klijent za živu simulaciju s automatskim ponovnim spajanjem.
import type { StateFrame } from "./types";

type FrameCb = (f: StateFrame) => void;
type StatusCb = (status: "connecting" | "connected" | "disconnected") => void;

export class SimSocket {
  private ws: WebSocket | null = null;
  private frameCb: FrameCb;
  private statusCb: StatusCb;
  private closed = false;

  constructor(frameCb: FrameCb, statusCb: StatusCb) {
    this.frameCb = frameCb;
    this.statusCb = statusCb;
  }

  connect(): void {
    this.statusCb("connecting");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws/sim`);
    this.ws.onopen = () => this.statusCb("connected");
    this.ws.onmessage = (ev) => {
      try {
        this.frameCb(JSON.parse(ev.data) as StateFrame);
      } catch {
        /* ignoriraj neispravan frame */
      }
    };
    this.ws.onclose = () => {
      this.statusCb("disconnected");
      if (!this.closed) setTimeout(() => this.connect(), 1200);
    };
    this.ws.onerror = () => this.ws?.close();
  }

  send(msg: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}
