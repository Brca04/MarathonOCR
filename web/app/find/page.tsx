'use client';

import { useCallback, useMemo, useState } from 'react';
import Nav from '@/components/Nav';
import SearchForm, { type SearchSubmit } from '@/components/SearchForm';
import RunnerView from '@/components/RunnerView';
import Lightbox from '@/components/Lightbox';
import Toast from '@/components/Toast';
import { findRunner, recordOrder, toGallery } from '@/lib/data';
import { PRICE_BUNDLE_EUR, PRICE_SINGLE_EUR, WATERMARK } from '@/lib/config';
import { signedOriginalUrl } from '@/lib/supabase';
import type { FindRunnerResult, GalleryPhoto, Runner } from '@/lib/types';

const REASON_COPY: Record<string, string> = {
  no_event: 'Photos for this event are not published yet.',
  dob_mismatch: 'Birthdate does not match this bib number.',
};

export default function FindPage() {
  const [bib, setBib] = useState('');
  const [dobText, setDobText] = useState('');
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

  const run = useCallback(
    async (nextBib: string, dobIso: string | null) => {
      const digits = nextBib.replace(/\D/g, '');
      if (!digits) return setError('Enter the number printed on your bib.');
      if (!dobIso) return setError('Enter your full birthdate as day, month, year.');

      setBusy(true);
      setError('');
      let res: FindRunnerResult;
      try {
        res = await findRunner(digits, dobIso);
      } catch (e) {
        setBusy(false);
        return setError('Could not reach the results service. Try again in a moment.');
      }
      setBusy(false);

      if (!res.ok) {
        if (res.reason === 'no_bib') {
          return setError(`No runner with bib ${digits} in this edition.`);
        }
        return setError(REASON_COPY[res.reason] ?? 'Something went wrong. Try again.');
      }

      setFound({ runner: res.runner, photos: toGallery(res.photos) });
      setLb(-1);
      window.scrollTo(0, 0);
    },
    [],
  );

  const onSubmit = useCallback(
    ({ bib: b, dobIso }: SearchSubmit) => {
      void run(b, dobIso);
    },
    [run],
  );

  const onDemo = useCallback(() => {
    setBib('1042');
    setDobText('14 · 03 · 1989');
    void run('1042', '1989-03-14');
  }, [run]);

  const searchAgain = useCallback(() => {
    setFound(null);
    setBib('');
    setDobText('');
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

  const buyAll = useCallback(() => {
    if (!found) return;
    if (ownedAll) return say('Preparing a ZIP of all originals…');
    setOwned((o) => ({ ...o, [`${found.runner.bib}:all`]: true }));
    void recordOrder(found.runner.bib, 'bundle', null, PRICE_BUNDLE_EUR);
    say('All photos unlocked');
  }, [found, ownedAll, say]);

  const buyOne = useCallback(() => {
    if (!found || lb < 0) return;
    const p = photos[lb];
    setOwned((o) => ({ ...o, [`${found.runner.bib}:${p.id}`]: true }));
    void recordOrder(found.runner.bib, 'single', p.id, PRICE_SINGLE_EUR);
    say('Purchased — original unlocked');
  }, [found, lb, photos, say]);

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
    say(`Downloading original (${p.dims})…`);
  }, [lb, photos, say]);

  return (
    <div
      style={{
        position: 'relative',
        minHeight: '100svh',
        background: '#070e1c',
        color: '#f2f5fb',
        overflowX: 'clip',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Nav active="find" />

      {found ? (
        <RunnerView
          runner={found.runner}
          photos={photos}
          ownedAll={ownedAll}
          onOpen={setLb}
          onBuyAll={buyAll}
          onSearchAgain={searchAgain}
        />
      ) : (
        <SearchForm
          bib={bib}
          setBib={(v) => {
            setBib(v);
            setError('');
          }}
          dobText={dobText}
          setDobText={(v) => {
            setDobText(v);
            setError('');
          }}
          error={error}
          busy={busy}
          onSubmit={onSubmit}
          onDemo={onDemo}
        />
      )}

      {lb >= 0 && photos[lb] ? (
        <Lightbox
          photos={photos}
          index={lb}
          owned={isOwned(photos[lb].id)}
          onClose={() => setLb(-1)}
          onStep={step}
          onBuy={buyOne}
          onDownloadPreview={() => say('Downloading watermarked preview…')}
          onDownloadOriginal={() => void downloadOriginal()}
        />
      ) : null}

      <Toast message={toast} />
    </div>
  );
}
