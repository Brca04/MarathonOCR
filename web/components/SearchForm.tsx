'use client';

import { useState } from 'react';
import { COURSE_MAP_SRC } from '@/lib/config';
import { dobToIso, formatDobInput, raceFromBib } from '@/lib/format';
import { isLive } from '@/lib/supabase';

const mono = (size = 10): React.CSSProperties => ({
  fontFamily: 'var(--mono)',
  fontSize: size,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: '#8b9bba',
});

export type SearchSubmit = { bib: string; dobIso: string | null };

export default function SearchForm({
  bib,
  setBib,
  dobText,
  setDobText,
  error,
  busy,
  onSubmit,
  onDemo,
}: {
  bib: string;
  setBib: (v: string) => void;
  dobText: string;
  setDobText: (v: string) => void;
  error: string;
  busy: boolean;
  onSubmit: (v: SearchSubmit) => void;
  onDemo: () => void;
}) {
  const [dirty, setDirty] = useState(false);
  const race = raceFromBib(bib);

  return (
    <main
      data-screen-label="Search"
      data-search-grid=""
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0,1.5fr) minmax(340px,520px)',
        minHeight: '100svh',
        width: '100%',
        animation: 'fade .4s ease both',
      }}
    >
      <div
        style={{
          position: 'relative',
          minHeight: 420,
          overflow: 'hidden',
          background: '#0e192e',
          borderRight: '1px solid #1c2a45',
        }}
      >
        <iframe
          src={COURSE_MAP_SRC}
          title="Zagreb marathon course map"
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            border: 0,
            display: 'block',
          }}
        />
        <div
          style={{
            position: 'absolute',
            left: 'clamp(16px,4vw,48px)',
            bottom: 20,
            display: 'grid',
            gap: 4,
            pointerEvents: 'none',
            textShadow: '0 1px 8px rgba(7,14,28,.9)',
          }}
        >
          <span style={mono()}>Course</span>
          <span style={{ fontSize: 14, fontWeight: 600, letterSpacing: '-.01em' }}>
            Start &amp; finish · Trg bana Jelačića
          </span>
        </div>
      </div>

      <form
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          setDirty(true);
          onSubmit({ bib, dobIso: dobToIso(dobText) });
        }}
        style={{
          display: 'grid',
          gap: 12,
          width: '100%',
          alignContent: 'center',
          padding: '112px clamp(20px,3vw,48px) clamp(24px,4vh,48px)',
          background: '#070e1c',
        }}
      >
        <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
          <span style={{ ...mono(11), color: '#3f82ff' }}>Photo search</span>
          <h2
            style={{
              margin: 0,
              fontWeight: 700,
              fontSize: 'clamp(26px,2.6vw,34px)',
              letterSpacing: '-.035em',
              lineHeight: 1.05,
            }}
          >
            Enter your bib number
          </h2>
          <p
            style={{
              margin: 0,
              fontSize: 14,
              lineHeight: 1.5,
              color: '#8b9bba',
              textWrap: 'pretty',
            }}
          >
            The number printed on your race bib, plus your birthdate to confirm it&apos;s you.
          </p>
        </div>

        {/* --- the bib itself ------------------------------------------------ */}
        <div
          style={{
            position: 'relative',
            background: '#f7f8fb',
            color: '#0a0a0a',
            borderRadius: 6,
            padding: '20px 18px 14px',
            display: 'grid',
            gap: 0,
          }}
        >
          {(['left', 'right'] as const).map((side) => (
            <span
              key={side}
              aria-hidden="true"
              style={{
                position: 'absolute',
                top: 8,
                [side]: 12,
                width: 6,
                height: 6,
                borderRadius: '50%',
                background: '#070e1c',
              }}
            />
          ))}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'baseline',
              gap: 12,
              padding: '0 4px',
            }}
          >
            <span
              style={{
                fontWeight: 800,
                fontSize: 'clamp(15px,1.6vw,18px)',
                letterSpacing: '-.01em',
                textTransform: 'uppercase',
                lineHeight: 1,
              }}
            >
              34. Zagrebački maraton
            </span>
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 10,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: '#4c5c7c',
                whiteSpace: 'nowrap',
              }}
            >
              Zagreb · 2026
            </span>
          </div>

          <label
            data-bib-band=""
            style={{
              position: 'relative',
              display: 'block',
              margin: '12px 0 0',
              background: '#0a0a0a',
              color: '#fff',
              borderRadius: 4,
              padding: '8px 28px 8px 32px',
              transition: 'box-shadow .2s',
            }}
          >
            <span
              aria-hidden="true"
              style={{
                position: 'absolute',
                left: 5,
                top: '50%',
                transform: 'translateY(-50%) rotate(-90deg)',
                fontFamily: 'var(--mono)',
                fontSize: 7,
                letterSpacing: '.12em',
                textTransform: 'uppercase',
                color: '#8b9bba',
                whiteSpace: 'nowrap',
              }}
            >
              11. listopada 2026.
            </span>
            <span
              style={{
                position: 'absolute',
                left: 0,
                width: 1,
                height: 1,
                overflow: 'hidden',
                clip: 'rect(0 0 0 0)',
              }}
            >
              Bib number
            </span>
            <input
              data-bib-input=""
              value={bib}
              onChange={(e) => setBib(e.target.value.replace(/\D/g, '').slice(0, 6))}
              inputMode="numeric"
              autoComplete="off"
              autoFocus
              placeholder="0000"
              style={{
                display: 'block',
                border: 0,
                outline: 0,
                background: 'transparent',
                color: '#fff',
                fontWeight: 900,
                fontSize: 'clamp(64px,8vw,96px)',
                letterSpacing: '-.02em',
                lineHeight: 1,
                textAlign: 'center',
                padding: 0,
                width: '100%',
                minWidth: 0,
                fontVariantNumeric: 'tabular-nums',
              }}
            />
          </label>

          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              gap: 12,
              marginTop: 12,
              padding: '10px 4px 0',
              borderTop: '1px solid #dfe3ec',
            }}
          >
            <span style={{ fontWeight: 800, fontSize: 20, letterSpacing: '-.02em', lineHeight: 1 }}>
              {race.label}
            </span>
            <span
              style={{
                fontFamily: 'var(--mono)',
                fontSize: 10,
                letterSpacing: '.1em',
                textTransform: 'uppercase',
                color: '#4c5c7c',
              }}
            >
              {race.name}
            </span>
          </div>
        </div>

        {/* --- birthdate ---------------------------------------------------- */}
        <label
          data-field=""
          className="field"
          style={{
            display: 'grid',
            gridTemplateColumns: 'auto 1fr',
            alignItems: 'center',
            gap: 14,
            padding: '14px 16px',
            borderRadius: 8,
            background: '#0e192e',
            border: '1px solid #1c2a45',
            transition: 'border-color .2s',
          }}
        >
          <span style={{ ...mono(), lineHeight: 1.5 }}>
            Birthdate
            <br />
            <span style={{ color: '#4c5c7c' }}>DD · MM · YYYY</span>
          </span>
          <input
            value={dobText}
            onChange={(e) => setDobText(formatDobInput(e.target.value))}
            inputMode="numeric"
            autoComplete="bday"
            aria-label="Birthdate, day month year"
            placeholder="14 · 03 · 1989"
            style={{
              border: 0,
              outline: 0,
              background: 'transparent',
              color: '#f2f5fb',
              fontFamily: 'var(--mono)',
              fontSize: 22,
              letterSpacing: '.04em',
              padding: 0,
              width: '100%',
              minWidth: 0,
              textAlign: 'right',
              fontVariantNumeric: 'tabular-nums',
            }}
          />
        </label>

        {error ? (
          <p
            role="alert"
            style={{
              margin: 0,
              padding: '12px 16px',
              borderRadius: 8,
              border: '1px solid rgba(255,120,120,.35)',
              fontSize: 14,
              lineHeight: 1.4,
              color: '#ffb3b3',
            }}
          >
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          className="btn-solid"
          disabled={busy}
          style={{
            border: 0,
            borderRadius: 8,
            background: '#f2f5fb',
            color: '#070e1c',
            fontWeight: 600,
            fontSize: 15,
            padding: '0 24px',
            height: 52,
            transition: 'background .2s',
            opacity: busy ? 0.7 : 1,
          }}
        >
          {busy ? 'Searching…' : 'Find my photos'}
        </button>

        {!isLive ? (
          <a
            href="#"
            className="link-mute"
            onClick={(e) => {
              e.preventDefault();
              onDemo();
            }}
            style={{
              justifySelf: 'center',
              padding: '8px 4px',
              fontSize: 13,
              textDecoration: 'underline',
              textUnderlineOffset: 4,
              textDecorationColor: 'rgba(139,155,186,.4)',
            }}
          >
            View a demo runner (bib 1042)
          </a>
        ) : null}

        {!isLive ? (
          <span style={{ ...mono(9), justifySelf: 'center', color: '#4c5c7c' }}>
            Demo data · no Supabase configured
          </span>
        ) : null}

        {dirty && !dobToIso(dobText) && dobText ? (
          <span style={{ ...mono(9), justifySelf: 'center', color: '#4c5c7c' }}>
            Birthdate needs all eight digits
          </span>
        ) : null}
      </form>
    </main>
  );
}
