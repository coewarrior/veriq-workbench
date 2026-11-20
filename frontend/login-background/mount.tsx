import { createRoot } from 'react-dom/client';
import { SylvaHero } from '@designcodeio/threeui';
import '@designcodeio/threeui/style.css';

// Use the source's supported live-frame adapter. Its HTML, geometry, shaders,
// pointer interaction and responsive scene remain unchanged on disk.
function loginPresentation(frame: HTMLIFrameElement) {
  const doc = frame.contentDocument;
  if (!doc?.querySelector('#hero')) return;
  doc.getElementById('login-presentation')?.remove();
  const style = doc.createElement('style');
  style.id = 'login-presentation';
  style.textContent = `
    html,body { width:100%; height:100%; overflow:hidden; }
    .hero { height:100vh; min-height:0; }
    .dock-wrap, .stage > * { visibility:hidden!important; pointer-events:none!important; }
  `;
  doc.head.append(style);
  // Remove hidden authored links from keyboard and accessibility navigation.
  doc.querySelectorAll('.dock-wrap, .stage > *').forEach(node => {
    node.setAttribute('inert',''); node.setAttribute('aria-hidden','true');
  });
  frame.title = '苔藓、花朵与蝴蝶的绿色场景';
  frame.tabIndex = -1;
  document.documentElement.classList.add('scene-loaded');
  frame.contentWindow?.dispatchEvent(new Event('resize'));
}
export function Scene() {
  return <div className="shader-frame">
    <SylvaHero variant="living-green" headingFont="lexend" bodyFont="lexend"
      headingWeight="300" bodyWeight="300" primaryColor="#ffffff"
      headingSize={63} bodySize={16.5} headingLetterSpacing={-0.006}
      applyScene={loginPresentation}/>
  </div>;
}
const root = document.getElementById('login-background');
if (root) createRoot(root).render(<Scene/>);
