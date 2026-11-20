// A build-time brand adaptation, not a replacement renderer. The registered
// ThreeUI sources remain byte-exact; only the badge's carved letter paths differ.
export const WORDMARK_START = '  /* ---- the window carries the Codex wordmark.';
export const WORDMARK_END = '  gm.restore(); ge.restore();';
export const VERIQ_WORDMARK = `  /* ---- VERIQ: carved into the original mask, using the same emission
         weights, centred layout and particle pass as the authored wordmark. ---- */
  const GLYPH_WIDTHS = { V: 0.56, E: 0.48, R: 0.54, I: 0.28, Q: 0.60 };
  const glyph = (ch, x, y, h) => {
    const w = h * GLYPH_WIDTHS[ch];
    ge.strokeStyle = W2G('edition');
    both(c => {
      c.beginPath();
      if (ch === 'V') {
        c.moveTo(x+w*0.06, y+h*0.06);
        c.lineTo(x+w*0.50, y+h*0.96);
        c.lineTo(x+w*0.94, y+h*0.06);
      } else if (ch === 'E') {
        c.moveTo(x+w*0.94, y+h*0.06);
        c.lineTo(x+w*0.10, y+h*0.06);
        c.lineTo(x+w*0.10, y+h*0.96);
        c.lineTo(x+w*0.94, y+h*0.96);
        c.moveTo(x+w*0.10, y+h*0.50);
        c.lineTo(x+w*0.80, y+h*0.50);
      } else if (ch === 'R') {
        c.moveTo(x+w*0.10, y+h*0.96);
        c.lineTo(x+w*0.10, y+h*0.06);
        c.lineTo(x+w*0.52, y+h*0.06);
        c.bezierCurveTo(x+w*1.05, y+h*0.06, x+w*1.05, y+h*0.50, x+w*0.52, y+h*0.50);
        c.lineTo(x+w*0.10, y+h*0.50);
        c.moveTo(x+w*0.52, y+h*0.50);
        c.lineTo(x+w*0.96, y+h*0.96);
      } else if (ch === 'I') {
        c.moveTo(x+w*0.08, y+h*0.06);
        c.lineTo(x+w*0.92, y+h*0.06);
        c.moveTo(x+w*0.50, y+h*0.06);
        c.lineTo(x+w*0.50, y+h*0.96);
        c.moveTo(x+w*0.08, y+h*0.96);
        c.lineTo(x+w*0.92, y+h*0.96);
      } else if (ch === 'Q') {
        c.ellipse(x+w*0.48, y+h*0.50, w*0.42, h*0.45, 0, 0, TAU);
        c.moveTo(x+w*0.59, y+h*0.73);
        c.lineTo(x+w*0.98, y+h*1.02);
      }
      c.stroke();
    });
    return w;
  };
  (() => {
    const str = 'VERIQ', h = 0.087*S, gap = h*0.11, cx = 0.500*S, cy = 0.512*S;
    document.documentElement.dataset.sparkWordmark = str;
    let tot = 0; for (const ch of str) tot += h*GLYPH_WIDTHS[ch] + gap; tot -= gap;
    gm.lineWidth = 0.0068*S; ge.lineWidth = 0.019*S;
    let x = cx - tot/2; const y = cy - h/2;
    for (const ch of str) x += glyph(ch, x, y, h) + gap;
  })();

`;

export function createVeriqBadgeSource(source) {
  const start = source.indexOf(WORDMARK_START);
  const end = source.indexOf(WORDMARK_END, start);
  if (start < 0 || end < 0 || source.indexOf(WORDMARK_START, start + 1) !== -1 ||
      !source.slice(start, end).includes("const str = 'Codex'")) {
    throw new Error('The registered SparkBadge wordmark block is unavailable');
  }
  return source.slice(0, start) + VERIQ_WORDMARK + source.slice(end);
}
