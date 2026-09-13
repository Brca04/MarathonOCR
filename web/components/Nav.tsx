'use client';

import Link from 'next/link';
import Switches from '@/components/Switches';
import { useT } from '@/components/AppContext';
import { BRAND_MARK } from '@/lib/config';

/**
 * With the landing hero and the photo search merged onto one screen there is
 * nowhere else to navigate, so the header is just the race's emblem — which
 * still returns you to the top — and the two switches.
 */
export default function Nav() {
  const t = useT();
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
            filter: 'drop-shadow(0 2px 12px rgba(0,0,0,.35))',
          }}
        />
      </Link>

      <Switches />
    </header>
  );
}
