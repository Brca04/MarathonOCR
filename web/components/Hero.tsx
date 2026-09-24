'use client';

import { useEffect, useRef, useState } from 'react';
import { getEventStats } from '@/lib/data';
import { easeOutQuart, fromSeconds, toSeconds } from '@/lib/format';
import { num } from '@/lib/i18n';
import { useApp } from '@/components/AppContext';
import { DEMO_STATS } from '@/lib/demo';
import type { EventStats } from '@/lib/types';
import { EVENT, eventTitle } from '@/lib/event';

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
 * underneath.
 */
function finishersYear(raceDate: string | null): number {
  if (!raceDate) return new Date().getFullYear() - 1;
  const d = new Date(raceDate);
  return d.getTime() <= Date.now() ? d.getFullYear() : d.getFullYear() - 1;
}

export default function Hero({ style }: { style?: React.CSSProperties } = {}) {
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
  // Editorial numbers (first edition, course record) only show when the event
  // has them; otherwise the strip falls back to what the gallery itself knows.
  const cells: { value: string; label: string; accent?: boolean }[] = [
    stats.finishers
      ? {
          value: num(lang, Math.round(stats.finishers * p)),
          // Before race day the count is last edition's; after it, this one's.
          label: t.statFinishers(finishersYear(stats.race_date)),
        }
      : { value: num(lang, Math.round((stats.photos || 0) * p)), label: t.statPhotos },
    stats.first_year
      ? { value: String(stats.first_year) + (lang === 'hr' ? '.' : ''), label: t.statFirstEdition }
      : { value: num(lang, Math.round((stats.tagged_bibs || 0) * p)), label: t.statBibs },
    { value: num(lang, (stats.distance_km ?? EVENT.raceKm ?? 42.195) * p, 3), label: t.statKm },
    stats.course_record
      ? { value: fromSeconds(recordSec * p), label: t.statRecord, accent: true }
      : {
          value: stats.race_date ? new Date(stats.race_date).getFullYear().toString() : '—',
          label: t.statYear,
          accent: true,
        },
  ];

  const title = eventTitle(lang);
  const accentAt = EVENT.accent ? title.indexOf(EVENT.accent) : -1;

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
        ...style,
      }}
    >
      {/* The photograph is the panel: it runs the full height and the copy sits
          straight on it — no deck, no blur, no fade, no shadow. Anything over
          the picture takes the fixed on-media colours. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={EVENT.heroImage}
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
            {accentAt < 0 ? (
              title
            ) : (
              <>
                {title.slice(0, accentAt)}
                <span style={{ color: 'var(--on-media-accent)' }}>{EVENT.accent}</span>
                {title.slice(accentAt + EVENT.accent.length)}
              </>
            )}
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

        {/* Mobile only (see globals.css): once the hero runs the full
            display, nothing on screen hints that the form is one scroll
            away, so a small bouncing cue does that job. */}
        <button
          type="button"
          data-scroll-hint=""
          aria-label={t.scrollHint}
          onClick={() => {
            document
              .querySelector('[data-search-grid] > form')
              ?.scrollIntoView({ behavior: 'smooth' });
          }}
          style={{
            display: 'none',
            width: '100%',
            border: 0,
            background: 'transparent',
            color: 'var(--on-media-mute)',
            padding: '4px 0 clamp(10px,2dvh,18px)',
            justifyContent: 'center',
            alignItems: 'center',
          }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
      </div>
    </div>
  );
}
