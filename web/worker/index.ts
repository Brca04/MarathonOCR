/**
 * Edge guard in front of the static site.
 *
 * Pages and scripts are static files; this Worker only runs for /data/*,
 * /api/* and /media/* (see `run_worker_first` in wrangler.jsonc).
 *
 *   POST /api/session   -> short-lived signed cookie. When TURNSTILE_SECRET is
 *                          set, a valid Cloudflare Turnstile token is required
 *                          first (invisible for normal visitors, a challenge
 *                          for bots).
 *   GET  /data/bib/*    -> needs that cookie. Each session may look up at most
 *                          BIB_QUOTA different bibs (30 by default), counted
 *                          exactly by a Durable Object per session; on top of
 *                          that, Cloudflare's per-location rate limits stop
 *                          floods. A runner looks up 1-5 bibs; a scraper has to
 *                          pass Turnstile again for every 30, which makes
 *                          harvesting a whole field slow and visible.
 *   GET  /data/_*       -> never served.
 *   GET  /media/*       -> event photos from the R2 bucket (binding MEDIA),
 *                          falling back to the asset store while a bucket is
 *                          still being filled.
 *
 * Fails open on configuration, never on abuse: without SESSION_SECRET the
 * cookie check is skipped but the per-IP limit still applies.
 */

interface RateLimit {
  limit(opts: { key: string }): Promise<{ success: boolean }>;
}

interface R2Object {
  body: ReadableStream;
  httpEtag: string;
  size: number;
  writeHttpMetadata(headers: Headers): void;
}

interface R2Bucket {
  get(key: string): Promise<R2Object | null>;
}

interface DurableObjectStub {
  fetch(req: Request | string, init?: RequestInit): Promise<Response>;
}

interface DurableObjectNamespace {
  idFromName(name: string): unknown;
  get(id: unknown): DurableObjectStub;
}

interface DurableObjectStorage {
  get<T>(key: string): Promise<T | undefined>;
  put(key: string, value: unknown): Promise<void>;
  deleteAll(): Promise<void>;
  setAlarm(when: number): Promise<void>;
  getAlarm(): Promise<number | null>;
}

interface DurableObjectState {
  storage: DurableObjectStorage;
  blockConcurrencyWhile<T>(fn: () => Promise<T>): Promise<T>;
}

interface Env {
  MEDIA?: R2Bucket;
  ASSETS: { fetch(req: Request | string): Promise<Response> };
  BIB_PER_SESSION: RateLimit;
  BIB_PER_IP: RateLimit;
  SESSION_PER_IP: RateLimit;
  QUOTA?: DurableObjectNamespace;
  BIB_QUOTA?: string;
  SESSION_SECRET?: string;
  TURNSTILE_SECRET?: string;
}

const COOKIE = 'mg_s';
// Short sessions: the page renews one silently when it expires.
const SESSION_SECONDS = 15 * 60;
const DEFAULT_BIB_QUOTA = 30;

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

type Session = { sid: string; exp: number };

async function verify(secret: string, value: string | null): Promise<Session | null> {
  if (!value) return null;
  const [sid, exp, sig] = value.split('.');
  if (!sid || !exp || !sig || Number(exp) < Date.now() / 1000) return null;
  const good = await hmac(secret, `${sid}.${exp}`);
  // Constant-time-ish compare; both strings are short and fixed-length.
  if (good.length !== sig.length) return null;
  let diff = 0;
  for (let i = 0; i < good.length; i++) diff |= good.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0 ? { sid, exp: Number(exp) } : null;
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

    if (url.pathname.startsWith('/media/')) {
      if (req.method !== 'GET' && req.method !== 'HEAD') return new Response(null, { status: 405 });
      const key = decodeURIComponent(url.pathname.slice(1));
      const obj = env.MEDIA && !key.includes('..') ? await env.MEDIA.get(key) : null;
      if (!obj) return env.ASSETS.fetch(req);
      const headers = new Headers();
      obj.writeHttpMetadata(headers);
      if (!headers.has('content-type')) headers.set('content-type', 'image/jpeg');
      headers.set('etag', obj.httpEtag);
      // Photo files are never rewritten in place, so browsers may keep them.
      headers.set('cache-control', 'public, max-age=604800');
      if (req.headers.get('if-none-match') === obj.httpEtag) return new Response(null, { status: 304, headers });
      headers.set('content-length', String(obj.size));
      return new Response(req.method === 'HEAD' ? null : obj.body, { headers });
    }
    if (url.pathname.startsWith('/data/_')) return new Response('Not found', { status: 404 });

    if (url.pathname.startsWith('/data/bib/')) {
      if (env.SESSION_SECRET) {
        const s = await verify(env.SESSION_SECRET, cookieValue(req, COOKIE));
        if (!s) return json(401, { ok: false, reason: 'session' });
        if (!(await env.BIB_PER_SESSION.limit({ key: s.sid })).success) return json(429, { ok: false, reason: 'rate_limited' });
        if (env.QUOTA) {
          const bib = url.pathname.slice('/data/bib/'.length).replace(/\.json$/, '');
          const max = Number(env.BIB_QUOTA) || DEFAULT_BIB_QUOTA;
          const stub = env.QUOTA.get(env.QUOTA.idFromName(s.sid));
          const q = await stub.fetch('https://quota/check', {
            method: 'POST',
            body: JSON.stringify({ bib, max, exp: s.exp }),
          });
          // The browser takes this as "start a new session" (and passes Turnstile again).
          if (q.status === 429) return json(429, { ok: false, reason: 'quota' });
        }
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

/**
 * One instance per session id. Remembers which bibs that session has looked
 * up and refuses new ones past the quota. Looking at the same bib again is
 * free, so a runner flipping between their own gallery and a friend's never
 * hits it. Storage is wiped by an alarm when the session expires.
 */
export class SessionQuota {
  constructor(private state: DurableObjectState) {}

  async fetch(req: Request): Promise<Response> {
    const { bib, max, exp } = (await req.json()) as { bib: string; max: number; exp: number };
    const seen = (await this.state.storage.get<string[]>('bibs')) ?? [];
    if (seen.includes(bib)) return new Response('ok');
    if (seen.length >= max) return new Response('quota', { status: 429 });
    seen.push(bib);
    await this.state.storage.put('bibs', seen);
    if ((await this.state.storage.getAlarm()) === null) {
      await this.state.storage.setAlarm(exp * 1000 + 60_000);
    }
    return new Response('ok');
  }

  async alarm(): Promise<void> {
    await this.state.storage.deleteAll();
  }
}
