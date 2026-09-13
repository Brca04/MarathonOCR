'use client';

import Link from 'next/link';

/**
 * The sliding pill nav from the design. `active` moves the white pill and flips
 * the two label colours; both links are real routes so the browser back button
 * and a shared URL behave.
 */
export default function Nav({ active }: { active: 'home' | 'find' }) {
  const onFind = active === 'find';
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
      <Link
        href="/"
        aria-label="Zagrebački maraton, home"
        style={{ display: 'flex', alignItems: 'center', gap: 12 }}
      >
        <span
          style={{
            width: 36,
            height: 36,
            borderRadius: '50%',
            background: '#3f82ff',
            display: 'grid',
            placeItems: 'center',
            fontWeight: 800,
            fontSize: 14,
            color: '#070e1c',
            letterSpacing: '-.04em',
          }}
        >
          34
        </span>
        <span data-logo-text="" style={{ display: 'grid', lineHeight: 1.1 }}>
          <span style={{ fontWeight: 600, fontSize: 15, letterSpacing: '-.01em' }}>
            Zagrebački maraton
          </span>
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10,
              letterSpacing: '.14em',
              textTransform: 'uppercase',
              color: '#8b9bba',
            }}
          >
            Official photo
          </span>
        </span>
      </Link>

      <nav
        aria-label="Primary"
        style={{
          position: 'relative',
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          padding: 4,
          borderRadius: 999,
          background: 'rgba(7,14,28,.55)',
          border: '1px solid rgba(242,245,251,.12)',
          backdropFilter: 'blur(12px)',
        }}
      >
        <span
          aria-hidden="true"
          style={{
            position: 'absolute',
            top: 4,
            bottom: 4,
            left: onFind ? '50%' : 4,
            width: 'calc(50% - 4px)',
            borderRadius: 999,
            background: '#f2f5fb',
            transition: 'left .4s cubic-bezier(.3,.7,.2,1)',
          }}
        />
        {(
          [
            { href: '/', label: 'Home', current: !onFind },
            { href: '/find', label: 'Find my photos', current: onFind },
          ] as const
        ).map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className="nav-link"
            aria-current={item.current ? 'page' : undefined}
            style={
              {
                position: 'relative',
                zIndex: 1,
                padding: '9px 18px',
                fontSize: 14,
                fontWeight: 600,
                textAlign: 'center',
                borderRadius: 999,
                transition: 'color .3s',
                whiteSpace: 'nowrap',
                '--nav-idle': item.current ? '#070e1c' : '#c4cee2',
                '--nav-hover': item.current ? '#070e1c' : '#f2f5fb',
              } as React.CSSProperties
            }
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
