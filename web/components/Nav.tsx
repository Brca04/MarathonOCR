'use client';

import Link from 'next/link';
import Switches from '@/components/Switches';
import { useT } from '@/components/AppContext';
import { BRAND_MARK } from '@/lib/config';

/**
 * The emblem stays on the left, the language switch on the right — shrinking
 * a touch on the runner profile (see `compact` below). The way home used to
 * live up here too; it now lives only at the bottom of the profile, past the
 * gallery, so this header stays just the emblem and the switch.
 */
export default function Nav({ onSearchAgain }: { onSearchAgain?: () => void }) {
  const t = useT();
  const inProfile = Boolean(onSearchAgain);
  return (
    <header
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 40,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: 16,
        padding: '16px clamp(16px,4vw,48px)',
      }}
    >
      {/* The race's own emblem, straight from the official site. */}
      <Link href="/" aria-label={t.navHome} style={{ display: 'flex', alignItems: 'center' }}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={BRAND_MARK}
          alt=""
          style={{
            display: 'block',
            height: 'clamp(40px,4.4vw,52px)',
            width: 'auto',
            // 336 × 400 — held so the header does not reflow while it loads.
            aspectRatio: '336 / 400',
            borderRadius: 6,
          }}
        />
      </Link>

      <Switches compact={inProfile} />
    </header>
  );
}
