// Tiny static server. Three.js ships ES modules only, and Chromium blocks
// module scripts over file://, so everything is served over 127.0.0.1.
import { createServer } from 'http';
import { readFile } from 'fs/promises';
import { extname, resolve, normalize } from 'path';
const TYPES = { '.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript',
  '.json':'application/json', '.css':'text/css', '.wav':'audio/wav', '.png':'image/png' };
export function serve(root, port = 0) {
  const srv = createServer(async (req, res) => {
    try {
      const url = decodeURIComponent(req.url.split('?')[0]);
      const file = resolve(root, '.' + normalize(url === '/' ? '/index.html' : url));
      if (!file.startsWith(resolve(root))) { res.writeHead(403).end(); return; }
      const body = await readFile(file);
      res.writeHead(200, { 'content-type': TYPES[extname(file)] || 'application/octet-stream' });
      res.end(body);
    } catch { res.writeHead(404).end('not found'); }
  });
  return new Promise(r => srv.listen(port, '127.0.0.1', () => r({ srv, port: srv.address().port })));
}
