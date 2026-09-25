'use client';

import { useEffect, useRef, useState } from 'react';
import { easeOutCubic, fromSeconds, toSeconds, trackMarks } from '@/lib/format';
import { dataTerm } from '@/lib/i18n';
import { useApp } from '@/components/AppContext';
import type { GalleryPhoto, Runner } from '@/lib/types';
import { EVENT_SLUG } from '@/lib/supabase';
import profilePhotos from '@/lib/profile-photos.json';

const mono = (size = 11): React.CSSProperties => ({
  fontFamily: 'var(--mono)',
  fontSize: size,
  letterSpacing: '.16em',
  textTransform: 'uppercase',
});

/**
 * The photo the runner screen opens on. The first photo is often a start-line
 * crowd where this runner is one face among many, so prefer photos with the
 * fewest bibs in them. Among those, take the last frame of the longest burst
 * (shots a few seconds apart): a runner coming towards the camera is largest
 * in the final frames. Without timestamps it falls back to the first photo.
 */
function pickCover(photos: GalleryPhoto[]): GalleryPhoto | undefined {
  if (photos.length < 2) return photos[0];
  const fewest = Math.min(...photos.map((p) => p.bibs_in_photo ?? Infinity));
  const solo = photos.filter((p) => (p.bibs_in_photo ?? Infinity) === fewest);
  const timed = solo
    .map((p) => ({ p, t: p.captured_at ? Date.parse(p.captured_at) : NaN }))
    .filter((x) => !Number.isNaN(x.t))
    .sort((a, b) => a.t - b.t);
  if (!timed.length) return solo[0];
  let best: typeof timed = [];
  let run: typeof timed = [];
  for (const x of timed) {
    if (run.length && x.t - run[run.length - 1].t > 5000) run = [];
    run.push(x);
    if (run.length >= best.length) best = [...run];
  }
  return best[best.length - 1].p;
}

type Shot = { photo?: string; position?: string };
const PROFILE_PHOTOS = profilePhotos as Record<string, Record<string, { desktop?: Shot; mobile?: Shot }>>;

/**
 * The runner-page photo for one screen shape: a hand-picked photo and crop from
 * lib/profile-photos.json (event slug -> bib -> desktop/mobile) when one is set
 * and that photo is in the runner's gallery, else the automatic cover.
 */
function profileShot(
  bib: string,
  kind: 'desktop' | 'mobile',
  photos: GalleryPhoto[],
  cover: GalleryPhoto | undefined,
  fallbackPosition: string,
): { src: string; position: string } {
  const pick = PROFILE_PHOTOS[EVENT_SLUG]?.[bib]?.[kind];
  const picked = pick?.photo ? photos.find((p) => p.file_name === pick.photo) : undefined;
  // A crop only fits the photo it was chosen for; with no photo named it applies to the cover.
  const usePick = picked || (pick && !pick.photo);
  return {
    src: (picked ?? cover)?.src ?? '/photos/zg-runner.jpg',
    position: (usePick && pick?.position) || fallbackPosition,
  };
}

/**
 * The runner screen. The only motion left is the one that carries meaning: the
 * marker runs the course track while the clock counts up to the finish time.
 * Nothing fades or rises in.
 */
export default function RunnerView({
  runner,
  photos,
  onOpen,
  onDownloadAll,
  onHome,
}: {
  runner: Runner;
  photos: GalleryPhoto[];
  onOpen: (index: number) => void;
  onDownloadAll: () => void;
  onHome: () => void;
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

  const cover = pickCover(photos);
  const desktop = profileShot(runner.bib, 'desktop', photos, cover, '48% 30%');
  const mobile = profileShot(runner.bib, 'mobile', photos, cover, '50% 30%');
  const pct = `${(prog * 100).toFixed(2)}%`;
  const clock = fromSeconds(toSeconds(runner.time) * prog);
  // A gallery built from photos alone has no results yet: hide the empty stats.
  const hasResult = Boolean(runner.time || runner.pace || runner.place_overall);
  const marks = trackMarks(String(runner.race_code), t);


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
            runner's numbers and the course track sit straight on it, in the
            fixed on-media colours. A phone shows only the middle third of a
            landscape photo, so it gets its own image (data-runner-photo-mobile,
            swapped in by globals.css): a hand-picked photo and crop from
            lib/profile-photos.json when there is one, else the same cover. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          data-runner-photo=""
          src={desktop.src}
          alt=""
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: desktop.position,
          }}
        />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          data-runner-photo-mobile=""
          src={mobile.src}
          alt=""
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            objectPosition: mobile.position,
            display: 'none',
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
                background: 'var(--card-bg, #f7f8fb)',
                color: '#0a0a0a',
                borderRadius: 14,
                padding: 'clamp(16px,2.4cqh,26px) clamp(20px,3vw,40px)',
              }}
            >
              {/* Bib, name and the finish stats now share one line — the
                  slimmer the row, the more of the photograph shows above it.
                  Only when the two groups don't fit side by side does the
                  stats group drop to its own line (data-hero-toprow below). */}
              <div
                data-hero-toprow=""
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: 'clamp(14px,2.4vw,32px)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'clamp(12px,1.6vw,18px)',
                    minWidth: 0,
                  }}
                >
                  <span
                    style={{
                      flex: 'none',
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
                  <h2
                    style={{
                      margin: 0,
                      minWidth: 0,
                      fontWeight: 700,
                      fontSize: 'clamp(22px,min(3.2cqw,5.6cqh),40px)',
                      letterSpacing: '-.03em',
                      lineHeight: 1,
                      textWrap: 'balance',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {runner.name}
                  </h2>
                </div>

                <div
                  data-runner-stats=""
                  style={{
                    display: hasResult ? 'flex' : 'none',
                    alignItems: 'flex-end',
                    justifyContent: 'flex-end',
                    gap: 'clamp(18px,2.8vw,40px)',
                    flexWrap: 'wrap',
                  }}
                >
                  <div>
                    <div style={{ ...mono(), color: 'var(--blue)', marginBottom: 4 }}>
                      {t.finishTime}
                    </div>
                    <div
                      style={{
                        fontSize: 'clamp(22px,min(2.9cqw,5.2cqh),34px)',
                        fontWeight: 800,
                        letterSpacing: '-.03em',
                        lineHeight: 1,
                        whiteSpace: 'nowrap',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {runner.time ?? '—'}
                    </div>
                  </div>
                  <div>
                    <div style={{ ...mono(), color: 'var(--card-mute, #4c5c7c)', marginBottom: 4 }}>{t.pace}</div>
                    <div
                      style={{
                        fontSize: 'clamp(22px,min(2.9cqw,5.2cqh),34px)',
                        fontWeight: 800,
                        letterSpacing: '-.03em',
                        lineHeight: 1,
                        whiteSpace: 'nowrap',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {runner.pace ?? '—'}
                      <span
                        style={{
                          fontSize: '.5em',
                          fontWeight: 500,
                          color: 'var(--card-mute, #4c5c7c)',
                          letterSpacing: 0,
                          marginLeft: '.2em',
                        }}
                      >
                        /km
                      </span>
                    </div>
                  </div>
                  <div>
                    <div style={{ ...mono(), color: 'var(--card-mute, #4c5c7c)', marginBottom: 4 }}>{t.place}</div>
                    <div
                      style={{
                        fontSize: 'clamp(22px,min(2.9cqw,5.2cqh),34px)',
                        fontWeight: 800,
                        letterSpacing: '-.03em',
                        lineHeight: 1,
                        whiteSpace: 'nowrap',
                        fontVariantNumeric: 'tabular-nums',
                      }}
                    >
                      {runner.place_overall ?? '—'}
                    </div>
                  </div>
                </div>
              </div>

              {/* --- course track --------------------------------------------- */}
              <div
                style={{
                  marginTop: 'clamp(12px,1.8cqh,20px)',
                  paddingTop: 'clamp(12px,1.8cqh,20px)',
                  borderTop: '1px solid var(--card-line, #dfe3ec)',
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
                      background: 'var(--card-line, #dfe3ec)',
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
                        visibility: runner.time ? 'visible' : 'hidden',
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
                          background: 'var(--card-line-2, #c2cbdb)',
                        }}
                      />
                      <span
                        style={{
                          ...mono(10),
                          letterSpacing: '.12em',
                          color: 'var(--card-mute, #4c5c7c)',
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
          padding: 'clamp(28px,4.5vh,52px) clamp(16px,4vw,48px) clamp(20px,3vh,32px)',
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
              {/* A grid, every tile the same shape — the actual photo keeps
                  its own proportions in the viewer (Lightbox uses p.ratio),
                  but here a fixed ratio is what keeps every row flush instead
                  of the columns drifting out of line as they fill. Nothing is
                  printed over a photograph — the course point, time and
                  match quality are all in the viewer. */}
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
                  style={{ position: 'relative', cursor: 'zoom-in', margin: 0 }}
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={p.thumb}
                    alt={p.hint}
                    loading="lazy"
                    style={{
                      display: 'block',
                      width: '100%',
                      height: '100%',
                      aspectRatio: '1 / 1',
                      objectFit: 'cover',
                      borderRadius: 10,
                      background: 'var(--panel)',
                    }}
                  />
                </figure>
              ))}
            </div>
          </>
        )}
      </section>

      {/* --- bottom actions: everything left to do once the photos are in
          view, in one row instead of scattered down the page --------------- */}
      {photos.length > 0 ? (
        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            flexWrap: 'wrap',
            gap: 12,
            padding: '0 clamp(16px,4vw,48px) clamp(28px,4.5vh,52px)',
          }}
        >
          <button
            type="button"
            onClick={onDownloadAll}
            className="btn-skew"
            style={{ padding: '0 18px', height: 40 }}
          >
            <span className="btn-skew-label" style={{ fontSize: 13 }}>
              {t.downloadAll}
            </span>
          </button>
        </div>
      ) : null}

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
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
          <a href="/privatnost/" className="link-mute">
            {t.footerPrivacy}
          </a>
          <a href="/kontakt/" className="link-mute">
            {t.footerContact}
          </a>
        </div>
      </footer>
    </main>
  );
}
