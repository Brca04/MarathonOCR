'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useT } from '@/components/AppContext';

/**
 * The search now lives on the landing page. Old /find links land here and get
 * sent home; a client redirect rather than `redirect()` because the site is a
 * static export, where a server redirect has nowhere to run.
 */
export default function FindPage() {
  const t = useT();
  const router = useRouter();
  useEffect(() => {
    router.replace('/');
  }, [router]);

  return (
    <main
      style={{
        minHeight: '100svh',
        display: 'grid',
        placeItems: 'center',
        background: 'var(--ink)',
        color: 'var(--mute)',
        fontSize: 14,
      }}
    >
      <noscript>
        <a href="/" style={{ color: 'var(--blue)' }}>
          {t.redirectLink}
        </a>
      </noscript>
    </main>
  );
}
