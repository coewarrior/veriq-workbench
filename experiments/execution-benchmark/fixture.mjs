// Synthetic local system. Only the grader can access the server-side event log.
import http from 'node:http';
import { readFile } from 'node:fs/promises';

export async function startFixture() {
  const runs = new Map();
  const page = await readFile(new URL('./fixture.html', import.meta.url));
  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, 'http://localhost');
    res.setHeader('Cache-Control', 'no-store');
    if (req.method === 'GET' && url.pathname === '/') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(page); return;
    }
    const s = runs.get(url.searchParams.get('run'));
    if (!s) { res.writeHead(404); res.end('Unknown isolated run'); return; }
    const respond = body => { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(body)); };
    if (req.method === 'GET' && url.pathname === '/state') { respond(view(s)); return; }
    if (req.method !== 'POST' || url.pathname !== '/op') { res.writeHead(404); res.end(); return; }
    let raw = ''; for await (const chunk of req) { raw += chunk; if (raw.length > 8192) { res.writeHead(413); res.end(); return; } }
    try {
      const data = JSON.parse(raw), event = { index: s.events.length, at: performance.now(), ...data };
      s.events.push(event);
      if (data.action === 'upload') {
        if (s.denied) s.feedback = '当前账号没有上传权限';
        else if (data.bytes === 0 && s.emptyBug) s.feedback = '';
        else if (s.rejectDuplicate && s.docs.some(d => d.name === data.name)) s.feedback = '同名文件已存在，原资料保留';
        else {
          const doc = { id: `d${++s.sequence}`, name: data.name, enabled: true, status: '解析中', fact: '费用 312 元' };
          s.docs.push(doc); s.feedback = '已接收';
          const timer = setTimeout(() => { doc.status = '就绪'; s.revision++; }, s.delay);
          s.timers.push(timer);
        }
      } else if (data.action === 'ask') {
        const enabled = s.docs.filter(d => d.enabled && d.status === '就绪');
        const chosen = enabled.length > s.threshold ? enabled.filter(d => data.ids.includes(d.id)) : enabled;
        if (!chosen.length) s.feedback = '请选择可用资料';
        else {
          s.answer = `费用 312 元；来源：${chosen.map(d => d.name).join('、')}`;
          s.history.push({ name: '本轮问答', answer: s.answer }); s.feedback = '回答完成';
        }
      } else if (data.action === 'toggle') {
        const doc = s.docs.find(d => d.id === data.id); if (doc) doc.enabled = !doc.enabled;
      } else if (data.action === 'delete') {
        s.docs = s.docs.filter(d => d.id !== data.id);
      } else if (data.action === 'rename') {
        if (s.history[0]) s.history[0].name = data.name;
      } else if (data.action === 'delete-history') s.history = [];
      else { res.writeHead(400); res.end('Unknown action'); return; }
      s.revision++; respond(view(s));
    } catch { res.writeHead(400); res.end('Invalid fixture request'); }
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return {
    origin: `http://127.0.0.1:${server.address().port}`,
    add(id, config) {
      const docs = Array.from({ length: config.initial || 0 }, (_, n) => ({ id: `seed${n}`, name: `seed-${n}.txt`, enabled: true, status: '就绪', fact: '费用 312 元' }));
      if (config.control) docs.push({ id: 'control', name: 'control.txt', enabled: true, status: '就绪', fact: '费用 312 元' });
      const s = { docs, history: config.control ? [{ name: '本轮问答', answer: '费用 312 元' }] : [],
        threshold: 10, delay: 40, confirmation: false, denied: false, rejectDuplicate: false, emptyBug: false,
        revision: 0, sequence: 0, answer: '', feedback: '', events: [], timers: [], ...config };
      runs.set(id, s); return s;
    },
    get: id => runs.get(id),
    async close() { for (const s of runs.values()) for (const t of s.timers) clearTimeout(t); await new Promise(r => server.close(r)); },
  };
}

function view(s) {
  return { docs: s.docs, history: s.history, threshold: s.threshold, answer: s.answer,
    feedback: s.feedback, revision: s.revision, confirmation: s.confirmation, denied: s.denied };
}
