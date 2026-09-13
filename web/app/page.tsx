'use client';

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Nav from '@/components/Nav';
import { useT } from '@/components/AppContext';
import Hero from '@/components/Hero';
import SearchForm, { type SearchSubmit } from '@/components/SearchForm';
import RunnerView from '@/components/RunnerView';
import Lightbox from '@/components/Lightbox';
import Toast from '@/components/Toast';
import { findRunner, recordOrder, toGallery } from '@/lib/data';
import { PRICE_BUNDLE_EUR, PRICE_SINGLE_EUR, WATERMARK } from '@/lib/config';
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
  const [owned, setOwned] = useState<Record<string, true>>({});
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
        return setError(res.reason === 'no_event' ? t.errNoEvent : t.errGeneric);
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
  const isOwned = useCallback(
    (photoId: string) => {
      if (!WATERMARK) return true;
      if (!found) return false;
      return Boolean(owned[`${found.runner.bib}:all`] || owned[`${found.runner.bib}:${photoId}`]);
    },
    [found, owned],
  );
  const ownedAll = useMemo(
    () => (!WATERMARK ? true : Boolean(found && owned[`${found.runner.bib}:all`])),
    [found, owned],
  );

  const step = useCallback(
    (delta: number) => {
      const n = photos.length;
      if (!n) return;
      setLb((i) => (i + delta + n) % n);
    },
    [photos.length],
  );

  /**
   * Unlocked the first time, this actually delivers the files the second:
   * one fetch-and-save per photo, since a static export has nothing to zip
   * them with server-side. Falls back to opening the photo in a new tab if a
   * fetch is blocked (a cross-origin host without permissive CORS).
   */
  const buyAll = useCallback(async () => {
    if (!found) return;

    if (!ownedAll) {
      setOwned((o) => ({ ...o, [`${found.runner.bib}:all`]: true }));
      void recordOrder(found.runner.bib, 'bundle', null, PRICE_BUNDLE_EUR);
      say(t.toastUnlockedAll);
      return;
    }

    if (photos.length === 0) return;
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
  }, [found, ownedAll, photos, say, t]);

  const buyOne = useCallback(() => {
    if (!found || lb < 0) return;
    const p = photos[lb];
    setOwned((o) => ({ ...o, [`${found.runner.bib}:${p.id}`]: true }));
    void recordOrder(found.runner.bib, 'single', p.id, PRICE_SINGLE_EUR);
    say(t.toastPurchased);
  }, [found, lb, photos, say, t]);

  const downloadOriginal = useCallback(async () => {
    const p = photos[lb];
    if (!p) return;
    if (p.original_path) {
      const url = await signedOriginalUrl(p.original_path);
      if (url) {
        window.open(url, '_blank', 'noopener');
        return;
      }
    }
    say(t.toastOriginal(p.dims));
  }, [lb, photos, say, t]);

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
          ownedAll={ownedAll}
          onOpen={setLb}
          onBuyAll={buyAll}
        />
      ) : (
        <main
          data-screen-label="Home"
          data-search-grid=""
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0,1.5fr) minmax(340px,520px)',
            minHeight: '100svh',
            width: '100%',
          }}
        >
          <Hero />
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
        </main>
      )}

      {!found ? (
        <footer
          style={{
            maxWidth: 1440,
            margin: '0 auto',
            padding: 'clamp(14px,2.2vh,20px) clamp(16px,4vw,48px) clamp(24px,4vh,40px)',
            borderTop: '1px solid var(--line)',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            gap: '10px 24px',
            fontSize: 12,
            color: 'var(--mute)',
            width: '100%',
          }}
        >
          <span>{t.footerRights}</span>
          <div style={{ display: 'flex', gap: 20 }}>
            <a href="#" className="link-mute">
              {t.footerPrivacy}
            </a>
            <a href="#" className="link-mute">
              {t.footerPhotographers}
            </a>
            <a href="#" className="link-mute">
              {t.footerContact}
            </a>
          </div>
        </footer>
      ) : null}

      {lb >= 0 && photos[lb] ? (
        <Lightbox
          photos={photos}
          index={lb}
          owned={isOwned(photos[lb].id)}
          onClose={() => setLb(-1)}
          onStep={step}
          onBuy={buyOne}
          onDownloadPreview={() => say(t.toastPreview)}
          onDownloadOriginal={() => void downloadOriginal()}
        />
      ) : null}

      <Toast message={toast} />
    </div>
  );
}
