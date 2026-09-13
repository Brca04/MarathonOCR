'use client';

import Link from 'next/link';
import Switches from '@/components/Switches';
import { useT } from '@/components/AppContext';
import { BRAND_MARK } from '@/lib/config';

/**
 * The emblem stays on the left and the language switch on the right. On a
 * runner's profile the way home sits by itself, centred on the header
 * regardless of how wide the logo or the switch are — passing
 * `onSearchAgain` is what turns that pill on, since the home screen has
 * nowhere else to go.
 */
export default function Nav({ onSearchAgain }: { onSearchAgain?: () => void }) {
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
          }}
        />
      </Link>

      {onSearchAgain ? (
        <button
          type="button"
          onClick={onSearchAgain}
          className="pill-glass"
          style={{
            position: 'absolute',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%,-50%)',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            padding: '9px 16px 9px 12px',
            borderRadius: 999,
            color: 'var(--on-media)',
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M3 9.5 12 3l9 6.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1V9.5Z" />
          </svg>
          {t.backToSearch}
        </button>
      ) : null}

      <Switches />
    </header>
  );
}
