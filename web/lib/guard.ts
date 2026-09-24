/**
 * Client side of the edge guard (worker/index.ts): get a session before the
 * first bib lookup, and a Cloudflare Turnstile token first when the site has a
 * site key. Turnstile runs in "interaction-only" mode, so a normal visitor
 * never sees it; a headless scraper gets a challenge it cannot pass.
 */
const SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITEKEY || '';

type Turnstile = {
  render: (el: HTMLElement, opts: Record<string, unknown>) => string;
  remove: (id: string) => void;
};
declare global {
  interface Window {
    turnstile?: Turnstile;
  }
}

let scriptLoading: Promise<void> | null = null;
function loadTurnstile(): Promise<void> {
  if (window.turnstile) return Promise.resolve();
  scriptLoading ??= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('turnstile'));
    document.head.appendChild(s);
  });
  return scriptLoading;
}

async function turnstileToken(): Promise<string | null> {
  if (!SITE_KEY) return null;
  await loadTurnstile();
  return new Promise((resolve) => {
    // The widget needs a place in the DOM; it only becomes visible if Cloudflare
    // decides this visitor must click the checkbox.
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:60';
    document.body.appendChild(host);
    let id = '';
    const done = (token: string | null) => {
      try {
        if (id) window.turnstile?.remove(id);
      } catch {
        /* already gone */
      }
      host.remove();
      resolve(token);
    };
    id = window.turnstile!.render(host, {
      sitekey: SITE_KEY,
      appearance: 'interaction-only',
      callback: (t: string) => done(t),
      'error-callback': () => done(null),
      'timeout-callback': () => done(null),
    });
  });
}

let session: Promise<boolean> | null = null;

/** Resolves true once the browser holds a valid session cookie (or none is needed). */
export function ensureSession(force = false): Promise<boolean> {
  if (force) session = null;
  session ??= (async () => {
    try {
      const token = await turnstileToken();
      const r = await fetch('/api/session', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token }),
        credentials: 'same-origin',
      });
      // 404: no guard Worker in front (local dev, plain static hosting).
      return r.ok || r.status === 404;
    } catch {
      return false;
    }
  })();
  return session;
}
