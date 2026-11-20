import { createRoot } from "react-dom/client";
import { Scene } from "./Scene";

const host = document.getElementById("signal-background");
if (host) {
  const root = createRoot(host);
  root.render(<Scene />);
  window.addEventListener("pagehide", (event) => {
    if (!event.persisted) root.unmount();
  }, { once: true });
}
