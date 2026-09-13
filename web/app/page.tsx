'use client';

import { useEffect, useRef, useState } from 'react';
import Nav from '@/components/Nav';
import { getEventStats } from '@/lib/data';
import { easeOutQuart, fromSeconds, toSeconds } from '@/lib/format';
import { DEMO_STATS } from '@/lib/demo';
import type { EventStats } from '@/lib/types';

const mono: React.CSSProperties = {
  fontFamily: 'var(--mono)',
  fontSize: 10,
  letterSpacing: '.12em',
  textTransform: 'uppercase',
  color: '#8b9bba',
};

const bigNum: React.CSSProperties = {
  fontSize: 'clamp(26px,min(4vw,5vh),56px)',
  fontWeight: 600,
  letterSpacing: '-.04em',
  lineHeight: 1,
  fontVariantNumeric: 'tabular-nums',
};

export default function LandingPage() {
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
      value: Math.round((stats.finishers || 0) * p).toLocaleString('en-US'),
      label: `Finishers ${stats.race_date ? new Date(stats.race_date).getFullYear() - 1 : 2025}`,
    },
    { value: String(stats.first_year ?? 1992), label: 'First edition' },
    { value: ((stats.distance_km ?? 42.195) * p).toFixed(3), label: 'Kilometres' },
    { value: fromSeconds(recordSec * p), label: 'Course record', accent: true },
  ];

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
      <Nav active="home" />

      <main
        data-screen-label="Landing"
        style={{
          flex: '1 1 auto',
          minHeight: '100svh',
          display: 'grid',
          gridTemplateRows: 'minmax(0,1fr) auto auto',
        }}
      >
        <section
          style={{
            position: 'relative',
            minHeight: '62svh',
            display: 'grid',
            alignItems: 'end',
            padding: 'clamp(24px,5vh,64px) clamp(16px,4vw,48px)',
            overflow: 'hidden',
          }}
        >
          <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/photos/zg-hero.jpg"
              alt="Runners cheering on the Zagreb marathon course"
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                objectPosition: 'center 30%',
                animation: 'settle 1.6s cubic-bezier(.2,.7,.2,1) both',
              }}
            />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                background:
                  'linear-gradient(180deg,rgba(7,14,28,.3) 0%,rgba(7,14,28,.15) 40%,rgba(7,14,28,.82) 78%,#070e1c 100%)',
              }}
            />
          </div>

          <div
            data-hero-copy=""
            style={{
              position: 'relative',
              display: 'grid',
              gridTemplateColumns: 'minmax(0,1fr) auto',
              alignItems: 'end',
              gap: 'clamp(20px,4vw,64px)',
              maxWidth: 1240,
              width: '100%',
              margin: '0 auto',
              animation: 'rise .9s cubic-bezier(.2,.7,.2,1) both',
            }}
          >
            <h1
              style={{
                margin: 0,
                fontWeight: 700,
                fontSize: 'clamp(36px,min(6.4vw,12vh),110px)',
                lineHeight: 0.9,
                letterSpacing: '-.045em',
                whiteSpace: 'nowrap',
              }}
            >
              {stats.edition ?? 34}. <span style={{ color: '#3f82ff' }}>Zagrebački</span> maraton
            </h1>
          </div>
        </section>

        <section style={{ padding: '0 clamp(16px,4vw,48px)' }}>
          <div
            style={{
              maxWidth: 1240,
              margin: '0 auto',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))',
              gap: 1,
              background: '#1c2a45',
              borderTop: '1px solid #1c2a45',
              borderBottom: '1px solid #1c2a45',
            }}
          >
            {cells.map((c, i) => (
              <div
                key={c.label}
                style={{
                  background: '#070e1c',
                  padding:
                    i === 0
                      ? 'clamp(14px,2.4vh,28px) 24px clamp(14px,2.4vh,28px) 0'
                      : i === cells.length - 1
                        ? 'clamp(14px,2.4vh,28px) 0 clamp(14px,2.4vh,28px) 24px'
                        : 'clamp(14px,2.4vh,28px) 24px',
                }}
              >
                <div style={{ ...bigNum, color: c.accent ? '#3f82ff' : undefined }}>{c.value}</div>
                <div style={{ ...mono, marginTop: 8 }}>{c.label}</div>
              </div>
            ))}
          </div>
        </section>

        <footer
          style={{
            padding: 'clamp(14px,2vh,24px) clamp(16px,4vw,48px)',
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            gap: '12px 24px',
            fontSize: 12,
            color: '#8b9bba',
          }}
        >
          <span>© 2026 Zagrebački maraton · Official race photography</span>
          <div style={{ display: 'flex', gap: 20 }}>
            <a href="#" className="link-mute">
              Privacy
            </a>
            <a href="#" className="link-mute">
              Photographers
            </a>
            <a href="#" className="link-mute">
              Contact
            </a>
          </div>
        </footer>
      </main>
    </div>
  );
}
