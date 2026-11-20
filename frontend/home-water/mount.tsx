import { createRoot } from "react-dom/client";
import { Scene } from "./Scene";

const host = document.getElementById("home-water");
if (host) {
  const root = createRoot(host);
  root.render(<Scene />);
  const forwardPointer = (event: PointerEvent) => {
    const rect = host.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    host.querySelector('iframe')?.contentWindow?.postMessage({
      type: 'workspace-water-pointer', kind: event.type,
      x: (event.clientX - rect.left) / rect.width,
      y: (event.clientY - rect.top) / rect.height,
    }, '*');
  };
  const events = ['pointermove', 'pointerdown', 'pointerup', 'pointerleave'] as const;
  events.forEach(type => document.addEventListener(type, forwardPointer, {capture:true, passive:true}));
  window.addEventListener("pagehide", event => {
    if (!event.persisted) {
      events.forEach(type => document.removeEventListener(type, forwardPointer, true));
      root.unmount();
    }
  }, { once: true });
}
