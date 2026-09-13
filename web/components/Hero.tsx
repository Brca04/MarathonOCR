'use client';

import { useEffect, useRef, useState } from 'react';
import { getEventStats } from '@/lib/data';
import { easeOutQuart, fromSeconds, toSeconds } from '@/lib/format';
import { num } from '@/lib/i18n';
import { useApp } from '@/components/AppContext';
import { DEMO_STATS } from '@/lib/demo';
import type { EventStats } from '@/lib/types';

const mono: React.CSSProperties = {
  fontFamily: 'var(--mono)',
  fontSize: 10,
  letterSpacing: '.12em',
  textTransform: 'uppercase',
  color: 'var(--on-media-mute)',
};

const bigNum: React.CSSProperties = {
  fontSize: 'clamp(22px,2.2vw,34px)',
  fontWeight: 600,
  letterSpacing: '-.04em',
  lineHeight: 1,
  fontVariantNumeric: 'tabular-nums',
};

/**
 * The landing hero, now the left panel of the single merged screen: the course
 * photograph, the edition title over it, and the event counters rolling up
 * underneath. It replaces the course map iframe that used to sit here.
 */
export default function Hero() {
  const { lang, t } = useApp();
  const [stats, setStats] = useState<EventStats>(DEMO_STATS);
  const [p, setP] = useState(0);
  const raf = useRef<number>(0);

  useEffect(() => {
    let live = true;
    getEventStats().then((s) => {
      if (live) setStats(s);
    });
    return () => {
      live = false;
    };
  }, []);

  // Counters roll up once on mount, easing out over 1.5s after a 300ms beat.
  useEffect(() => {
    const t0 = performance.now();
    const dur = 1500;
    const delay = 300;
    const tick = (now: number) => {
      const x = easeOutQuart(Math.min(1, Math.max(0, (now - t0 - delay) / dur)));
      setP(x);
      if (x < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf.current);
  }, []);

  const recordSec = toSeconds(stats.course_record);
  const cells: { value: string; label: string; accent?: boolean }[] = [
    {
      value: num(lang, Math.round((stats.finishers || 0) * p)),
      label: t.statFinishers(stats.race_date ? new Date(stats.race_date).getFullYear() - 1 : 2025),
    },
    {
      value: String(stats.first_year ?? 1992) + (lang === 'hr' ? '.' : ''),
      label: t.statFirstEdition,
    },
    { value: num(lang, (stats.distance_km ?? 42.195) * p, 3), label: t.statKm },
    { value: fromSeconds(recordSec * p), label: t.statRecord, accent: true },
  ];

  return (
    <div
      data-hero-panel=""
      style={{
        position: 'relative',
        minHeight: 420,
        overflow: 'hidden',
        // Measuring itself lets the stat strip lay out against the panel
        // rather than the window.
        containerType: 'inline-size',
        background: 'var(--panel)',
        borderRight: '1px solid var(--line)',
        display: 'grid',
        gridTemplateRows: 'minmax(0,1fr) auto',
      }}
    >
      {/* The photograph is the panel: it runs the full height and the copy sits
          straight on it — no deck, no blur, no fade, no shadow. Anything over
          the picture takes the fixed on-media colours. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/photos/zg-hero.jpg"
        alt={t.heroAlt}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          objectPosition: 'center 30%',
        }}
      />

      {/* Holds the photograph open above the copy. */}
      <div data-hero-space="" aria-hidden="true" style={{ minHeight: 200 }} />

      <div
        data-on-media=""
        style={{
          position: 'relative',
          color: 'var(--on-media)',
        }}
      >
        <div
          data-hero-copy=""
          style={{
            padding: 'clamp(20px,3.4vh,40px) clamp(16px,4vw,48px) clamp(16px,2.6vh,28px)',
          }}
        >
          <h1
            style={{
              margin: 0,
              fontWeight: 700,
              fontSize: 'clamp(32px,min(4.6vw,10vh),72px)',
              lineHeight: 0.9,
              letterSpacing: '-.045em',
              textWrap: 'balance',
            }}
          >
            {stats.edition ?? 34}.{' '}
            <span style={{ color: 'var(--on-media-accent)' }}>Zagrebački</span> maraton
          </h1>
        </div>

        <div data-hero-stats="" style={{ padding: '0 clamp(16px,4vw,48px)' }}>
          {/* Nothing but hairlines: the photograph shows between the numbers,
              rather than a panel of its own. */}
          <div
            style={{
              display: 'grid',
              background: 'transparent',
              borderTop: '1px solid var(--media-rule)',
              borderBottom: '1px solid var(--media-rule)',
            }}
          >
            {cells.map((c) => (
              <div
                key={c.label}
                style={{
                  background: 'transparent',
                  padding: 'clamp(12px,2vh,22px) 20px',
                }}
              >
                <div
                  style={{
                    ...bigNum,
                    color: c.accent ? 'var(--on-media-accent)' : undefined,
                  }}
                >
                  {c.value}
                </div>
                <div style={{ ...mono, marginTop: 8 }}>{c.label}</div>
              </div>
            ))}
          </div>
        </div>

        <footer
          style={{
            padding: 'clamp(14px,2vh,24px) clamp(16px,4vw,48px)',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            gap: '12px 24px',
            fontSize: 12,
            color: 'var(--on-media-mute)',
          }}
        >
          <span>{t.footerRights}</span>
          <div style={{ display: 'flex', gap: 20 }}>
            <a href="#" className="link-media">
              {t.footerPrivacy}
            </a>
            <a href="#" className="link-media">
              {t.footerPhotographers}
            </a>
            <a href="#" className="link-media">
              {t.footerContact}
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
