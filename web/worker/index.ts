/**
 * Edge guard in front of the static site.
 *
 * Everything is still static files; this Worker only runs for /data/* and
 * /api/* (see `run_worker_first` in wrangler.jsonc). Photos, pages and scripts
 * never touch it, so they stay free and unlimited.
 *
 *   POST /api/session   -> short-lived signed cookie. When TURNSTILE_SECRET is
 *                          set, a valid Cloudflare Turnstile token is required
 *                          first (invisible for normal visitors, a challenge
 *                          for bots).
 *   GET  /data/bib/*    -> needs that cookie, and is rate limited per session
 *                          and per IP. A scraper walking bib 1..10000 hits the
 *                          limit within seconds; a runner never notices it.
 *   GET  /data/_*       -> never served.
 *
 * Fails open on configuration, never on abuse: without SESSION_SECRET the
 * cookie check is skipped but the per-IP limit still applies.
 */

interface RateLimit {
  limit(opts: { key: string }): Promise<{ success: boolean }>;
}

interface Env {
  ASSETS: { fetch(req: Request | string): Promise<Response> };
  BIB_PER_SESSION: RateLimit;
  BIB_PER_IP: RateLimit;
  SESSION_PER_IP: RateLimit;
  SESSION_SECRET?: string;
  TURNSTILE_SECRET?: string;
}

const COOKIE = 'mg_s';
const SESSION_SECONDS = 30 * 60;

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers },
  });

const b64url = (buf: ArrayBuffer) =>
  btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');

async function hmac(secret: string, data: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    'raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign'],
  );
  return b64url(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(data)));
}

/** "<sid>.<exp>.<sig>" — no server state, verified with SESSION_SECRET. */
async function issue(secret: string): Promise<string> {
  const sid = b64url(crypto.getRandomValues(new Uint8Array(12)).buffer);
  const exp = Math.floor(Date.now() / 1000) + SESSION_SECONDS;
  return `${sid}.${exp}.${await hmac(secret, `${sid}.${exp}`)}`;
}

async function verify(secret: string, value: string | null): Promise<string | null> {
  if (!value) return null;
  const [sid, exp, sig] = value.split('.');
  if (!sid || !exp || !sig || Number(exp) < Date.now() / 1000) return null;
  const good = await hmac(secret, `${sid}.${exp}`);
  // Constant-time-ish compare; both strings are short and fixed-length.
  if (good.length !== sig.length) return null;
  let diff = 0;
  for (let i = 0; i < good.length; i++) diff |= good.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0 ? sid : null;
}

function cookieValue(req: Request, name: string): string | null {
  const m = (req.headers.get('cookie') || '').match(new RegExp(`(?:^|;\\s*)${name}=([^;]+)`));
  return m ? decodeURIComponent(m[1]) : null;
}

async function turnstileOk(secret: string, token: unknown, ip: string): Promise<boolean> {
  if (typeof token !== 'string' || !token) return false;
  const form = new FormData();
  form.append('secret', secret);
  form.append('response', token);
  form.append('remoteip', ip);
  try {
    const r = await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body: form });
    const out = (await r.json()) as { success?: boolean };
    return Boolean(out.success);
  } catch {
    return false;
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);
    const ip = req.headers.get('cf-connecting-ip') || 'unknown';

    if (url.pathname === '/api/session') {
      if (req.method !== 'POST') return json(405, { ok: false });
      if (!(await env.SESSION_PER_IP.limit({ key: ip })).success) return json(429, { ok: false, reason: 'rate_limited' });
      if (env.TURNSTILE_SECRET) {
        const body = (await req.json().catch(() => ({}))) as { token?: string };
        if (!(await turnstileOk(env.TURNSTILE_SECRET, body.token, ip))) return json(403, { ok: false, reason: 'challenge' });
      }
      if (!env.SESSION_SECRET) return json(200, { ok: true, mode: 'open' });
      const value = await issue(env.SESSION_SECRET);
      return json(200, { ok: true }, {
        'set-cookie': `${COOKIE}=${value}; Path=/data; Max-Age=${SESSION_SECONDS}; HttpOnly; Secure; SameSite=Strict`,
      });
    }

    if (url.pathname.startsWith('/api/')) return json(404, { ok: false });
    if (url.pathname.startsWith('/data/_')) return new Response('Not found', { status: 404 });

    if (url.pathname.startsWith('/data/bib/')) {
      let sid: string | null = null;
      if (env.SESSION_SECRET) {
        sid = await verify(env.SESSION_SECRET, cookieValue(req, COOKIE));
        if (!sid) return json(401, { ok: false, reason: 'session' });
        if (!(await env.BIB_PER_SESSION.limit({ key: sid })).success) return json(429, { ok: false, reason: 'rate_limited' });
      }
      if (!(await env.BIB_PER_IP.limit({ key: ip })).success) return json(429, { ok: false, reason: 'rate_limited' });

      const res = await env.ASSETS.fetch(new Request(url.origin + url.pathname, { method: 'GET' }));
      if (res.status === 404) return json(404, { ok: false, reason: 'no_bib' });
      const out = new Response(res.body, res);
      // Only this visitor's browser may keep it; nothing shared in between.
      out.headers.set('cache-control', 'private, max-age=300');
      return out;
    }

    return env.ASSETS.fetch(req);
  },
};
