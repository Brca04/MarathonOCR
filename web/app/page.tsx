'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Nav from '@/components/Nav';
import { useT } from '@/components/AppContext';
import Hero from '@/components/Hero';
import SearchForm, { type SearchSubmit } from '@/components/SearchForm';
import RunnerView from '@/components/RunnerView';
import Lightbox from '@/components/Lightbox';
import Toast from '@/components/Toast';
import { findRunner, toGallery } from '@/lib/data';
import { signedOriginalUrl } from '@/lib/supabase';
import type { FindRunnerResult, GalleryPhoto, Runner } from '@/lib/types';

/**
 * One screen: the landing hero and the bib search live side by side, and the
 * runner's gallery takes over the whole page once a search lands.
 */
export default function HomePage() {
  // useSearchParams needs a boundary in a statically exported page.
  return (
    <Suspense fallback={null}>
      <Home />
    </Suspense>
  );
}

function Home() {
  const t = useT();
  const [bib, setBib] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [found, setFound] = useState<{ runner: Runner; photos: GalleryPhoto[] } | null>(null);
  const [lb, setLb] = useState(-1);
  const [toast, setToast] = useState('');

  const say = useCallback((message: string) => {
    setToast(message);
    window.setTimeout(() => setToast((t) => (t === message ? '' : t)), 2400);
  }, []);

  /**
   * `push` is false when the search was triggered by the URL itself — a shared
   * link or the back button — so the entry that caused it is not duplicated.
   */
  const run = useCallback(
    async (nextBib: string, push = true) => {
      const digits = nextBib.replace(/\D/g, '');
      if (!digits) return setError(t.errNoBib);

      setBusy(true);
      setError('');
      let res: FindRunnerResult;
      try {
        res = await findRunner(digits);
      } catch (e) {
        setBusy(false);
        return setError(t.errOffline);
      }
      setBusy(false);

      if (!res.ok) {
        if (res.reason === 'no_bib') {
          return setError(t.errUnknownBib(digits));
        }
        return setError(
          res.reason === 'no_event' ? t.errNoEvent : res.reason === 'rate_limited' ? t.errBusy : t.errGeneric,
        );
      }

      setFound({ runner: res.runner, photos: toGallery(res.photos) });
      setLb(-1);
      if (push) window.history.pushState({ bib: digits }, '', `?bib=${digits}`);
      window.scrollTo(0, 0);
    },
    [t],
  );

  const onSubmit = useCallback(
    ({ bib: b }: SearchSubmit) => {
      void run(b);
    },
    [run],
  );

  /**
   * The profile lives at ?bib=1042, which makes it linkable, survives a reload
   * and — the point of it — gives the browser's back button somewhere to go.
   * The URL is the single source of truth for which screen is showing, which is
   * what makes every route back to the search work: the back button, the mark
   * in the header and the button on the profile all just change it. A popstate
   * listener alone would miss the header link, since a client-side navigation
   * does not fire one.
   */
  const params = useSearchParams();
  const wanted = params.get('bib');
  const runRef = useRef(run);
  runRef.current = run;
  const shown = found?.runner.bib ?? null;

  useEffect(() => {
    if (!wanted) {
      setFound(null);
      setBib('');
      setError('');
      setLb(-1);
      window.scrollTo(0, 0);
      return;
    }
    if (wanted === shown) return;
    setBib(wanted);
    void runRef.current(wanted, false);
  }, [wanted, shown]);

  const searchAgain = useCallback(() => {
    // Walk back when this profile is an entry we pushed, so the link and the
    // back button leave the history in the same state. Someone who arrived
    // straight on a shared ?bib= link has nothing behind them, so that entry is
    // replaced instead — going "back" must never leave the site.
    if (window.history.state?.bib) {
      window.history.back();
      return;
    }
    window.history.replaceState(null, '', window.location.pathname);
    setFound(null);
    setBib('');
    setError('');
    setLb(-1);
    window.scrollTo(0, 0);
  }, []);

  const photos = found?.photos ?? [];
  const step = useCallback(
    (delta: number) => {
      const n = photos.length;
      if (!n) return;
      setLb((i) => (i + delta + n) % n);
    },
    [photos.length],
  );

  /**
   * One fetch-and-save per photo, since a static export has nothing to zip
   * them with server-side. Falls back to opening the photo in a new tab if a
   * fetch is blocked (a cross-origin host without permissive CORS).
   */
  const downloadAll = useCallback(async () => {
    if (!found || photos.length === 0) return;
    say(t.toastZip);
    for (let i = 0; i < photos.length; i++) {
      const p = photos[i];
      let url = p.src;
      if (p.original_path) {
        const signed = await signedOriginalUrl(p.original_path);
        if (signed) url = signed;
      }
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        const ext = url.split(/[?#]/)[0].split('.').pop() || 'jpg';
        const a = document.createElement('a');
        a.href = blobUrl;
        a.download = `${found.runner.bib}-${i + 1}.${ext}`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(blobUrl);
      } catch {
        window.open(url, '_blank', 'noopener');
      }
      if (i < photos.length - 1) await new Promise((r) => setTimeout(r, 200));
    }
  }, [found, photos, say, t]);

  /**
   * Same fetch-and-save approach as downloadAll: signedOriginalUrl only resolves
   * once Supabase is actually configured (it's null in the demo event), so
   * without it this fell straight through to a "here's the size" toast and
   * never saved anything. Falling back to the preview (p.src) — which is
   * always a real, reachable image — means the button actually downloads
   * something in every case, demo included.
   */
  const downloadOriginal = useCallback(async () => {
    const p = photos[lb];
    if (!p || !found) return;
    let url = p.src;
    if (p.original_path) {
      const signed = await signedOriginalUrl(p.original_path);
      if (signed) url = signed;
    }
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(String(res.status));
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const ext = url.split(/[?#]/)[0].split('.').pop() || 'jpg';
      const a = document.createElement('a');
      a.href = blobUrl;
      a.download = `${found.runner.bib}-${lb + 1}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(blobUrl);
    } catch {
      window.open(url, '_blank', 'noopener');
    }
  }, [lb, photos, found]);

  return (
    <div
      style={{
        position: 'relative',
        minHeight: '100svh',
        background: 'var(--ink)',
        color: 'var(--paper)',
        overflowX: 'clip',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Nav onSearchAgain={found ? searchAgain : undefined} />

      {found ? (
        <RunnerView
          runner={found.runner}
          photos={photos}
          onOpen={setLb}
          onDownloadAll={downloadAll}
          onHome={searchAgain}
        />
      ) : (
        // The home screen is budgeted to exactly one viewport. The hero
        // photograph now runs the full height of the screen on the left —
        // the form and the footer share that same height stacked on the
        // right, so the footer sits under the form rather than as a strip
        // cutting across the photograph too.
        <div
          data-home-screen=""
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: '100svh',
            width: '100%',
          }}
        >
          <main
            data-screen-label="Home"
            data-search-grid=""
            style={{
              display: 'grid',
              gridTemplateColumns: 'minmax(0,1.5fr) minmax(340px,520px)',
              gridTemplateRows: 'minmax(0,1fr) auto',
              flex: '1 1 auto',
              minHeight: 0,
              width: '100%',
            }}
          >
            <Hero style={{ gridColumn: 1, gridRow: '1 / -1' }} />
            <SearchForm
              bib={bib}
              setBib={(v) => {
                setBib(v);
                setError('');
              }}
              error={error}
              busy={busy}
              onSubmit={onSubmit}
            />

            {/* Stacked and centred rather than spread edge-to-edge — this
                column is narrow, and a copyright line plus three links never
                fit on one line here anyway, so they're arranged for that
                instead of fighting it. */}
            <footer
              style={{
                gridColumn: 2,
                gridRow: 2,
                padding: 'clamp(8px,1.6dvh,20px) clamp(16px,4vw,48px) clamp(10px,2dvh,24px)',
                borderTop: '1px solid var(--line)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                gap: 8,
                fontSize: 12,
                color: 'var(--mute)',
                width: '100%',
              }}
            >
              <span>{t.footerRights}</span>
              <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 20 }}>
                <a href="/privatnost/" className="link-mute">
                  {t.footerPrivacy}
                </a>
                <a href="/kontakt/" className="link-mute">
                  {t.footerContact}
                </a>
              </div>
            </footer>
          </main>
        </div>
      )}

      {lb >= 0 && photos[lb] ? (
        <Lightbox
          photos={photos}
          index={lb}
          onClose={() => setLb(-1)}
          onStep={step}
          onDownloadOriginal={() => void downloadOriginal()}
        />
      ) : null}

      <Toast message={toast} />
    </div>
  );
}
