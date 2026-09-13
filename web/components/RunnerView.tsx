'use client';

import { useEffect, useRef, useState } from 'react';
import { PRICE_BUNDLE_EUR, WATERMARK } from '@/lib/config';
import { easeOutCubic, fromSeconds, toSeconds, trackMarks } from '@/lib/format';
import type { GalleryPhoto, Runner } from '@/lib/types';

const mono = (size = 11): React.CSSProperties => ({
  fontFamily: 'var(--mono)',
  fontSize: size,
  letterSpacing: '.16em',
  textTransform: 'uppercase',
});

/**
 * The runner screen. Two animations from the design are load-bearing for the
 * feel of it, so they are reproduced rather than approximated:
 *
 *  - a 3.4s run along the course track, with the clock counting up to the
 *    finish time, easing out;
 *  - finish time, then pace, then place, each rising in 550ms apart once the
 *    run lands.
 */
export default function RunnerView({
  runner,
  photos,
  ownedAll,
  onOpen,
  onBuyAll,
  onSearchAgain,
}: {
  runner: Runner;
  photos: GalleryPhoto[];
  ownedAll: boolean;
  onOpen: (index: number) => void;
  onBuyAll: () => void;
  onSearchAgain: () => void;
}) {
  const [prog, setProg] = useState(0);
  const [stage, setStage] = useState(0);
  const raf = useRef<number>(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    const dur = 3400;
    const delay = 500;
    const t0 = performance.now();
    setProg(0);
    setStage(0);
    const tick = (now: number) => {
      const x = Math.min(1, Math.max(0, (now - t0 - delay) / dur));
      setProg(easeOutCubic(x));
      if (x < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    timers.current = [150, 700, 1150].map((extra, i) =>
      setTimeout(() => setStage(i + 1), delay + dur + extra),
    );
    return () => {
      cancelAnimationFrame(raf.current);
      timers.current.forEach(clearTimeout);
    };
  }, [runner.bib]);

  const pct = `${(prog * 100).toFixed(2)}%`;
  const clock = fromSeconds(toSeconds(runner.time) * prog);
  const marks = trackMarks(String(runner.race_code));
  const points = new Set(photos.map((p) => p.course_point)).size;
  const fuzzy = photos.filter((p) => p.match_kind === 'fuzzy').length;

  const reveal = (n: number, y: string) => ({
    opacity: stage >= n ? 1 : 0,
    transform: stage >= n ? 'none' : `translateY(${y})`,
    transition:
      'opacity .8s cubic-bezier(.2,.7,.2,1), transform .8s cubic-bezier(.2,.7,.2,1)',
  });

  return (
    <main data-screen-label="Runner" style={{ width: '100%', animation: 'fade .5s ease both' }}>
      <div
        style={{
          position: 'relative',
          width: '100%',
          minHeight: '100svh',
          containerType: 'size',
          overflow: 'hidden',
          background: '#0e192e',
          display: 'grid',
          gridTemplateRows: '1fr auto',
          isolation: 'isolate',
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={photos[0]?.src ?? '/photos/zg-runner.jpg'}
          alt=""
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: '48% 30%',
            animation: 'settle 1.8s cubic-bezier(.2,.7,.2,1) both',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background:
              'linear-gradient(180deg,rgba(7,14,28,.5) 0%,rgba(7,14,28,.15) 35%,rgba(7,14,28,.78) 70%,#070e1c 100%)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'linear-gradient(90deg,rgba(7,14,28,.55),transparent 60%)',
          }}
        />

        <div
          data-hero-grid=""
          style={{
            position: 'relative',
            zIndex: 1,
            alignSelf: 'end',
            display: 'grid',
            gridTemplateColumns: 'minmax(0,1fr) auto',
            gap: 'clamp(24px,4vw,64px)',
            alignItems: 'end',
            padding: '140px clamp(16px,4vw,48px) clamp(24px,4cqh,48px)',
            maxWidth: 1440,
            width: '100%',
            margin: '0 auto',
          }}
        >
          <div style={{ animation: 'rise .8s cubic-bezier(.2,.7,.2,1) both', minWidth: 0 }}>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                alignItems: 'center',
                gap: 10,
                marginBottom: 'clamp(14px,2.5cqh,24px)',
              }}
            >
              <span
                style={{
                  fontFamily: 'var(--mono)',
                  fontSize: 'clamp(13px,1.4cqw,18px)',
                  fontWeight: 500,
                  padding: '6px 12px',
                  borderRadius: 6,
                  background: '#f2f5fb',
                  color: '#070e1c',
                  letterSpacing: '.02em',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {runner.bib}
              </span>
              <span style={{ ...mono(11), letterSpacing: '.14em', color: '#c4cee2' }}>
                {[runner.race, runner.category, runner.club].filter(Boolean).join(' · ')}
              </span>
            </div>
            <h2
              style={{
                margin: 0,
                fontWeight: 700,
                fontSize: 'clamp(44px,min(7cqw,12cqh),120px)',
                letterSpacing: '-.035em',
                lineHeight: 0.88,
                textWrap: 'balance',
              }}
            >
              {runner.name}
            </h2>
          </div>

          <div
            style={{
              display: 'grid',
              gap: 'clamp(16px,3cqh,32px)',
              justifyItems: 'end',
              textAlign: 'right',
              minWidth: 0,
            }}
          >
            <div style={reveal(1, '24px')}>
              <div style={{ ...mono(), color: '#3f82ff', marginBottom: 8 }}>Finish time</div>
              <div
                style={{
                  fontSize: 'clamp(72px,min(13cqw,24cqh),240px)',
                  fontWeight: 800,
                  letterSpacing: '-.045em',
                  lineHeight: 0.85,
                  whiteSpace: 'nowrap',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {runner.time ?? '—'}
              </div>
            </div>

            <div
              style={{
                display: 'flex',
                gap: 'clamp(24px,4cqw,56px)',
                justifyContent: 'flex-end',
                flexWrap: 'wrap',
              }}
            >
              <div style={reveal(2, '18px')}>
                <div style={{ ...mono(), color: '#8b9bba', marginBottom: 6 }}>Pace</div>
                <div
                  style={{
                    fontSize: 'clamp(36px,min(5.5cqw,9cqh),88px)',
                    fontWeight: 700,
                    letterSpacing: '-.04em',
                    lineHeight: 1,
                    whiteSpace: 'nowrap',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {runner.pace ?? '—'}
                  <span
                    style={{
                      fontSize: '.4em',
                      fontWeight: 500,
                      color: '#c4cee2',
                      letterSpacing: 0,
                      marginLeft: '.2em',
                    }}
                  >
                    /km
                  </span>
                </div>
              </div>
              <div style={reveal(3, '18px')}>
                <div style={{ ...mono(), color: '#8b9bba', marginBottom: 6 }}>Place</div>
                <div
                  style={{
                    fontSize: 'clamp(36px,min(5.5cqw,9cqh),88px)',
                    fontWeight: 700,
                    letterSpacing: '-.04em',
                    lineHeight: 1,
                    whiteSpace: 'nowrap',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {runner.place_overall ?? '—'}
                  <span
                    style={{
                      fontSize: '.4em',
                      fontWeight: 500,
                      color: '#c4cee2',
                      letterSpacing: 0,
                      marginLeft: '.25em',
                    }}
                  >
                    · {runner.place_category ?? '—'} {runner.category ?? ''}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* --- course track ------------------------------------------------- */}
        <div
          style={{
            position: 'relative',
            zIndex: 1,
            padding: '0 clamp(16px,4vw,48px) clamp(20px,3cqh,36px)',
            maxWidth: 1440,
            width: '100%',
            margin: '0 auto',
            animation: 'fade .5s .2s ease both',
          }}
        >
          <div style={{ position: 'relative', height: 70 }}>
            <div
              style={{
                position: 'absolute',
                left: 0,
                right: 0,
                top: 44,
                height: 1,
                background: 'rgba(242,245,251,.2)',
              }}
            />
            <div
              style={{ position: 'absolute', left: 0, top: 44, height: 2, background: '#3f82ff', width: pct }}
            />
            <div style={{ position: 'absolute', top: 0, left: pct, width: 0 }}>
              <span
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 2,
                  transform: `translateX(${(-prog * 100).toFixed(1)}%)`,
                  padding: '5px 10px',
                  borderRadius: 6,
                  background: '#f2f5fb',
                  color: '#070e1c',
                  fontFamily: 'var(--mono)',
                  fontSize: 13,
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  letterSpacing: '.02em',
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {clock}
              </span>
              <span
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 44,
                  width: 10,
                  height: 10,
                  transform: 'translate(-50%,-50%)',
                  borderRadius: '50%',
                  background: '#3f82ff',
                  boxShadow: '0 0 0 3px #070e1c',
                }}
              />
            </div>
            {marks.map((m) => (
              <div
                key={m.label}
                style={{
                  position: 'absolute',
                  top: 50,
                  left: m.left,
                  transform: `translateX(${m.shift})`,
                  display: 'grid',
                  gap: 5,
                  justifyItems: m.align,
                }}
              >
                <span style={{ width: 1, height: 6, background: 'rgba(242,245,251,.4)' }} />
                <span
                  style={{
                    ...mono(10),
                    letterSpacing: '.12em',
                    color: '#8b9bba',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {m.label}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* --- gallery ------------------------------------------------------- */}
      <section style={{ maxWidth: 1440, margin: '0 auto', padding: '40px clamp(16px,4vw,48px) 120px' }}>
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            justifyContent: 'space-between',
            alignItems: 'end',
            gap: '16px 24px',
            padding: '0 0 24px',
            borderBottom: '1px solid #1c2a45',
            marginBottom: 24,
          }}
        >
          <div>
            <div style={{ ...mono(), color: '#3f82ff', marginBottom: 10 }}>Your photos</div>
            <h3
              style={{
                margin: 0,
                fontWeight: 600,
                fontSize: 'clamp(24px,3vw,36px)',
                letterSpacing: '-.03em',
                lineHeight: 1,
              }}
            >
              {photos.length} photos{' '}
              <span style={{ color: '#8b9bba', fontWeight: 500 }}>
                from {points} point{points === 1 ? '' : 's'} on the course
              </span>
            </h3>
            {fuzzy > 0 ? (
              <div style={{ ...mono(10), letterSpacing: '.12em', color: '#4c5c7c', marginTop: 10 }}>
                {fuzzy} likely match{fuzzy === 1 ? '' : 'es'} · the number was partly unreadable
              </div>
            ) : null}
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <a
              href="#"
              className="link-mute"
              onClick={(e) => {
                e.preventDefault();
                onSearchAgain();
              }}
              style={{ fontSize: 14, padding: '12px 6px' }}
            >
              Not you? Search again
            </a>
            <button
              onClick={onBuyAll}
              className="btn-ghost"
              style={{
                border: '1px solid rgba(242,245,251,.18)',
                background: 'transparent',
                color: '#f2f5fb',
                borderRadius: 8,
                padding: '0 20px',
                height: 44,
                fontSize: 14,
                fontWeight: 600,
                transition: 'border-color .2s,color .2s',
              }}
            >
              {ownedAll ? 'Download all originals' : `Unlock all · €${PRICE_BUNDLE_EUR}`}
            </button>
          </div>
        </div>

        {photos.length === 0 ? (
          <p style={{ color: '#8b9bba', fontSize: 15, lineHeight: 1.6, maxWidth: 560 }}>
            No photos are tagged with bib {runner.bib} yet. Photos are added as the photographers
            upload and the numbers are read — check back later in the day.
          </p>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill,minmax(min(100%,260px),1fr))',
              gap: 10,
            }}
          >
            {photos.map((p, i) => (
              <figure
                key={p.id}
                className="tile"
                role="button"
                tabIndex={0}
                onClick={() => onOpen(i)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpen(i);
                  }
                }}
                aria-label={`Open photo ${p.course_point ?? ''} ${p.clock}`}
                style={{
                  margin: 0,
                  position: 'relative',
                  aspectRatio: '4/3',
                  borderRadius: 8,
                  overflow: 'hidden',
                  background: '#0e192e',
                  cursor: 'zoom-in',
                  boxShadow: 'inset 0 0 0 1px rgba(242,245,251,.06)',
                  animation: 'fade .6s ease both',
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={p.src}
                  alt={p.hint}
                  loading="lazy"
                  style={{
                    position: 'absolute',
                    inset: 0,
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    filter: WATERMARK && !ownedAll ? 'saturate(.92)' : undefined,
                  }}
                />
                {p.match_kind === 'fuzzy' ? (
                  <span
                    title={`Recognised as ${p.read_as}`}
                    style={{
                      position: 'absolute',
                      top: 10,
                      left: 10,
                      padding: '4px 8px',
                      borderRadius: 5,
                      background: 'rgba(7,14,28,.78)',
                      border: '1px solid rgba(143,182,255,.35)',
                      color: '#8fb6ff',
                      fontFamily: 'var(--mono)',
                      fontSize: 9,
                      letterSpacing: '.1em',
                      textTransform: 'uppercase',
                    }}
                  >
                    Likely
                  </span>
                ) : null}
                <figcaption
                  style={{
                    position: 'absolute',
                    left: 0,
                    right: 0,
                    bottom: 0,
                    padding: '40px 14px 12px',
                    background: 'linear-gradient(transparent,rgba(7,14,28,.9))',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'end',
                    gap: 8,
                    fontSize: 11,
                    fontFamily: 'var(--mono)',
                    letterSpacing: '.08em',
                    textTransform: 'uppercase',
                    pointerEvents: 'none',
                  }}
                >
                  <span style={{ color: '#8fb6ff' }}>{p.course_point}</span>
                  <span style={{ color: '#c4cee2', fontVariantNumeric: 'tabular-nums' }}>
                    {p.clock}
                  </span>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
