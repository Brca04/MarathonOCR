'use client';

import { useEffect, useRef, useState } from 'react';
import { PRICE_BUNDLE_EUR, WATERMARK } from '@/lib/config';
import { easeOutCubic, fromSeconds, toSeconds, trackMarks } from '@/lib/format';
import { dataTerm } from '@/lib/i18n';
import { useApp } from '@/components/AppContext';
import type { GalleryPhoto, Runner } from '@/lib/types';

const mono = (size = 11): React.CSSProperties => ({
  fontFamily: 'var(--mono)',
  fontSize: size,
  letterSpacing: '.16em',
  textTransform: 'uppercase',
});

/**
 * The runner screen. The only motion left is the one that carries meaning: the
 * marker runs the course track while the clock counts up to the finish time.
 * Nothing fades or rises in.
 */
export default function RunnerView({
  runner,
  photos,
  ownedAll,
  onOpen,
  onBuyAll,
}: {
  runner: Runner;
  photos: GalleryPhoto[];
  ownedAll: boolean;
  onOpen: (index: number) => void;
  onBuyAll: () => void;
}) {
  const { lang, t } = useApp();
  const [prog, setProg] = useState(0);
  const raf = useRef<number>(0);

  useEffect(() => {
    const dur = 3400;
    const delay = 500;
    const t0 = performance.now();
    setProg(0);
    const tick = (now: number) => {
      const x = Math.min(1, Math.max(0, (now - t0 - delay) / dur));
      setProg(easeOutCubic(x));
      if (x < 1) raf.current = requestAnimationFrame(tick);
    };
    raf.current = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(raf.current);
    };
  }, [runner.bib]);

  const pct = `${(prog * 100).toFixed(2)}%`;
  const clock = fromSeconds(toSeconds(runner.time) * prog);
  const marks = trackMarks(String(runner.race_code), t);

  // No staged reveal: the numbers are simply there when the screen is.
  const reveal = (_n: number, _y: string): React.CSSProperties | undefined => undefined;

  return (
    <main data-screen-label="Runner" style={{ width: '100%' }}>
      <div
        style={{
          position: 'relative',
          width: '100%',
          minHeight: '100svh',
          containerType: 'size',
          overflow: 'hidden',
          background: 'var(--ink)',
          display: 'grid',
          gridTemplateRows: 'minmax(0,1fr) auto auto',
          isolation: 'isolate',
        }}
      >
        {/* The photograph is the screen: it runs the full height and the
            runner's numbers and the course track sit straight on it — no deck,
            no blur — in the fixed on-media colours. */}
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
          }}
        />

        <div aria-hidden="true" />

        <div
          data-on-media=""
          style={{
            position: 'relative',
            zIndex: 1,
            color: 'var(--on-media)',
          }}
        >
          {/* One white tab holds everything — the bib, the runner's name and
              the finish stats — rather than splitting the numbers out into
              their own card while the name sits bare on the photo. The back
              link now lives in the header, next to the emblem. */}
          <div
            style={{
              position: 'relative',
              zIndex: 1,
              padding: 'clamp(20px,3.2cqh,40px) clamp(16px,4vw,48px) clamp(20px,3cqh,36px)',
              maxWidth: 1440,
              width: '100%',
              margin: '0 auto',
            }}
          >
            <div
              data-hero-grid=""
              style={{
                background: '#f7f8fb',
                color: '#0a0a0a',
                borderRadius: 14,
                display: 'grid',
                gridTemplateColumns: 'minmax(0,1fr) auto',
                gap: 'clamp(24px,4vw,64px)',
                alignItems: 'end',
                padding: 'clamp(20px,3cqh,36px) clamp(20px,3vw,40px)',
              }}
            >
              <div style={{ minWidth: 0 }}>
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
                      background: '#0a0a0a',
                      color: '#fff',
                      letterSpacing: '.02em',
                      fontVariantNumeric: 'tabular-nums',
                    }}
                  >
                    {runner.bib}
                  </span>
                  <span
                    style={{
                      ...mono(11),
                      letterSpacing: '.14em',
                      color: '#4c5c7c',
                    }}
                  >
                    {[dataTerm(lang, runner.race), runner.category, runner.club]
                      .filter(Boolean)
                      .join(' · ')}
                  </span>
                </div>
                <h2
                  style={{
                    margin: 0,
                    fontWeight: 700,
                    fontSize: 'clamp(36px,min(6.4cqw,11cqh),108px)',
                    letterSpacing: '-.035em',
                    lineHeight: 0.9,
                    textWrap: 'balance',
                  }}
                >
                  {runner.name}
                </h2>
              </div>

              <div
                data-runner-stats=""
                style={{
                  display: 'grid',
                  gap: 'clamp(14px,2.2cqh,26px)',
                  justifyItems: 'end',
                  textAlign: 'right',
                  minWidth: 0,
                }}
              >
                <div style={reveal(1, '24px')}>
                  <div style={{ ...mono(), color: 'var(--blue)', marginBottom: 8 }}>
                    {t.finishTime}
                  </div>
                  <div
                    style={{
                      fontSize: 'clamp(40px,min(8cqw,14cqh),120px)',
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
                    gap: 'clamp(20px,3.2cqw,44px)',
                    justifyContent: 'flex-end',
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={reveal(2, '18px')}>
                    <div style={{ ...mono(), color: '#4c5c7c', marginBottom: 6 }}>
                      {t.pace}
                    </div>
                    <div
                      style={{
                        fontSize: 'clamp(26px,min(4.2cqw,7cqh),52px)',
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
                          color: '#4c5c7c',
                          letterSpacing: 0,
                          marginLeft: '.2em',
                        }}
                      >
                        /km
                      </span>
                    </div>
                  </div>
                  <div style={reveal(3, '18px')}>
                    <div style={{ ...mono(), color: '#4c5c7c', marginBottom: 6 }}>
                      {t.place}
                    </div>
                    <div
                      style={{
                        fontSize: 'clamp(26px,min(4.2cqw,7cqh),52px)',
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
                          color: '#4c5c7c',
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

              {/* --- course track, folded into the same tab ------------------ */}
              <div
                style={{
                  gridColumn: '1 / -1',
                  marginTop: 'clamp(6px,1.4cqh,14px)',
                  paddingTop: 'clamp(20px,3cqh,32px)',
                  borderTop: '1px solid #dfe3ec',
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
                      background: '#dfe3ec',
                    }}
                  />
                  <div
                    style={{
                      position: 'absolute',
                      left: 0,
                      top: 44,
                      height: 2,
                      background: 'var(--blue)',
                      width: pct,
                    }}
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
                        background: '#0a0a0a',
                        color: '#fff',
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
                        background: 'var(--blue)',
                      }}
                    />
                  </div>
                  {marks.map((m, i) => (
                    <div
                      key={m.label}
                      data-mark-index={i}
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
                      <span
                        style={{
                          width: 1,
                          height: 6,
                          background: '#c2cbdb',
                        }}
                      />
                      <span
                        style={{
                          ...mono(10),
                          letterSpacing: '.12em',
                          color: '#4c5c7c',
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
          </div>
        </div>
      </div>

      {/* --- gallery ------------------------------------------------------- */}
      <section
        style={{
          maxWidth: 1440,
          margin: '0 auto',
          padding: 'clamp(28px,4.5vh,52px) clamp(16px,4vw,48px) clamp(56px,9vh,104px)',
        }}
      >
        {/* One line, centred: how many photographs were found, and the one
            action that belongs to all of them. */}
        <div style={{ textAlign: 'center', padding: '0 0 clamp(20px,3.4vh,36px)' }}>
          <h3
            style={{
              margin: 0,
              fontWeight: 600,
              fontSize: 'clamp(20px,2.4vw,30px)',
              letterSpacing: '-.02em',
              lineHeight: 1.2,
              textWrap: 'balance',
            }}
          >
            {t.photosFound(photos.length)}
          </h3>
        </div>

        {photos.length === 0 ? (
          <p
            style={{
              color: 'var(--mute)',
              fontSize: 15,
              lineHeight: 1.6,
              maxWidth: 560,
            }}
          >
            {t.noPhotos(runner.bib)}
          </p>
        ) : (
          <>
            <div data-gallery="">
              {/* Masonry: every photograph keeps its own shape and the columns
                  just hold them. Nothing is printed over a photograph — the
                  course point, time and match quality are all in the viewer. */}
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
                  aria-label={t.openPhoto(dataTerm(lang, p.course_point), p.clock)}
                  // No inline margin here: the row gap belongs to the gallery's
                  // stylesheet, and an inline `margin: 0` would silently win.
                  style={{ position: 'relative', cursor: 'zoom-in' }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={p.src}
                    alt={p.hint}
                    loading="lazy"
                    style={{
                      display: 'block',
                      width: '100%',
                      height: 'auto',
                      aspectRatio: p.ratio,
                      objectFit: 'cover',
                      borderRadius: 10,
                      background: 'var(--panel)',
                    }}
                  />
                </figure>
              ))}
            </div>

            {/* The one action that belongs to all of them, now after the
                photographs rather than before — a decision made looking at
                what you are buying. */}
            <div style={{ textAlign: 'center', padding: 'clamp(28px,4.5vh,52px) 0 0' }}>
              <button
                onClick={onBuyAll}
                className="btn-ghost"
                style={{
                  border: '1px solid var(--line-2)',
                  background: 'transparent',
                  color: 'var(--paper)',
                  borderRadius: 8,
                  padding: '0 20px',
                  height: 44,
                  fontSize: 14,
                  fontWeight: 600,
                  transition: 'border-color .2s,color .2s',
                }}
              >
                {ownedAll ? t.downloadAll : t.unlockAll(PRICE_BUNDLE_EUR)}
              </button>
            </div>
          </>
        )}
      </section>

      {/* --- footer ---------------------------------------------------------- */}
      <footer
        style={{
          maxWidth: 1440,
          margin: '0 auto',
          padding: 'clamp(14px,2.2vh,20px) clamp(16px,4vw,48px) clamp(24px,4vh,40px)',
          borderTop: '1px solid var(--line)',
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          gap: '10px 24px',
          fontSize: 12,
          color: 'var(--mute)',
        }}
      >
        <span>{t.footerRights}</span>
        <div style={{ display: 'flex', gap: 20 }}>
          <a href="#" className="link-mute">
            {t.footerPrivacy}
          </a>
          <a href="#" className="link-mute">
            {t.footerPhotographers}
          </a>
          <a href="#" className="link-mute">
            {t.footerContact}
          </a>
        </div>
      </footer>
    </main>
  );
}
