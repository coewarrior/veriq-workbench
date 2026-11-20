import { createRoot } from "react-dom/client";
import { Scene } from "./Scene";
document.querySelectorAll<HTMLElement>(".home-induction").forEach(host => {
  const link = host.closest<HTMLAnchorElement>("a[data-induction-label]");
  if (!link) return;
  const root = createRoot(host);
  root.render(<Scene />);
  const post = (kind: string, label?: string) => host.querySelector("iframe")?.contentWindow?.postMessage({type:"workspace-induction", kind, label}, "*");
  const events = ["mouseenter", "mouseleave", "focus", "blur", "mousedown", "mouseup", "click"];
  const forward = (event: Event) => post(event.type);
  events.forEach(kind => link.addEventListener(kind, forward));
  const ready = (event: MessageEvent) => {
    const frame = host.querySelector("iframe");
    if (frame && event.source === frame.contentWindow && event.data?.type === "workspace-induction-ready") {
      frame.tabIndex = -1;
      link.classList.add("induction-ready");
      post("label", link.dataset.inductionLabel);
      if (link.matches(":hover")) post("mouseenter");
      if (document.activeElement === link) post("focus");
    }
  };
  window.addEventListener("message", ready);
  window.addEventListener("pagehide", event => {
    if (!event.persisted) {
      events.forEach(kind => link.removeEventListener(kind, forward));
      window.removeEventListener("message", ready);
      root.unmount();
    }
  }, {once:true});
});
