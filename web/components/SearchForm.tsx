'use client';

import { useEffect, useRef, useState } from 'react';
import { EVENT, EVENT_YEAR, eventDateLabel, eventTitle } from '@/lib/event';
import { raceFromBib } from '@/lib/format';
import { useT } from '@/components/AppContext';

export type SearchSubmit = { bib: string };

export default function SearchForm({
  bib,
  setBib,
  error,
  busy,
  onSubmit,
}: {
  bib: string;
  setBib: (v: string) => void;
  error: string;
  busy: boolean;
  onSubmit: (v: SearchSubmit) => void;
}) {
  const t = useT();
  const race = raceFromBib(bib, t);
  const [agreed, setAgreed] = useState(false);
  const bibInputRef = useRef<HTMLInputElement>(null);

  // Autofocus on load, but not on a touch device: focusing this giant
  // numeric input immediately pops the keyboard and, on iOS Safari
  // specifically, can trigger a jarring auto-zoom that crops the bib card
  // to a sliver of itself before the page has even settled.
  useEffect(() => {
    if (window.matchMedia('(pointer: fine)').matches) {
      bibInputRef.current?.focus();
    }
  }, []);

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ bib });
      }}
      style={{
        display: 'grid',
        gap: 12,
        width: '100%',
        alignContent: 'center',
        padding: '112px clamp(20px,3vw,48px) clamp(24px,4vh,48px)',
        background: 'var(--ink)',
      }}
    >
      <div style={{ display: 'grid', gap: 8, marginBottom: 10, textAlign: 'center' }}>
        <h2
          style={{
            margin: 0,
            fontWeight: 700,
            fontSize: 'clamp(26px,2.6vw,34px)',
            letterSpacing: '-.035em',
            lineHeight: 1.05,
          }}
        >
          {t.searchTitle}
        </h2>
        <p
          style={{
            margin: 0,
            fontSize: 14,
            lineHeight: 1.5,
            color: 'var(--mute)',
            textWrap: 'pretty',
          }}
        >
          {t.searchSub}
        </p>
      </div>

      {/* --- the bib itself ------------------------------------------------ */}
      <div
        style={{
          position: 'relative',
          background: 'var(--card-bg, #f7f8fb)',
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
              background: '#0a0a0a',
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
            {eventTitle(t.lang)}
          </span>
          <span
            style={{
              fontFamily: 'var(--mono)',
              fontSize: 10,
              letterSpacing: '.1em',
              textTransform: 'uppercase',
              color: 'var(--card-mute, #4c5c7c)',
              whiteSpace: 'nowrap',
            }}
          >
            {[EVENT.city, EVENT_YEAR].filter(Boolean).join(' · ')}
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
          }}
        >
          <span
            data-bib-date=""
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
              color: 'var(--card-faint, #8b9bba)',
              whiteSpace: 'nowrap',
            }}
          >
            {eventDateLabel(t.lang)}
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
            {t.bibLabel}
          </span>
          <input
            ref={bibInputRef}
            data-bib-input=""
            value={bib}
            onChange={(e) => setBib(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            autoComplete="off"
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
            borderTop: '1px solid var(--card-line, #dfe3ec)',
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
              color: 'var(--card-mute, #4c5c7c)',
            }}
          >
            {race.name}
          </span>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          style={{
            margin: 0,
            padding: '12px 16px',
            borderRadius: 8,
            border: '1px solid var(--danger-line)',
            fontSize: 14,
            lineHeight: 1.4,
            color: 'var(--danger)',
          }}
        >
          {error}
        </p>
      ) : null}

      {/* --- privacy consent ------------------------------------------------ */}
      <label
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          gap: 10,
          padding: '2px 4px',
          cursor: 'pointer',
        }}
      >
        <input
          type="checkbox"
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          style={{
            marginTop: 2,
            width: 18,
            height: 18,
            flexShrink: 0,
            accentColor: 'var(--blue)',
            cursor: 'pointer',
          }}
        />
        <span style={{ fontSize: 13, lineHeight: 1.5, color: 'var(--mute)' }}>
          {t.consentPrefix}
          <a
            href="#"
            className="link-mute"
            onClick={(e) => e.stopPropagation()}
            style={{ textDecoration: 'underline', textUnderlineOffset: 3 }}
          >
            {t.consentLinkText}
          </a>
          {t.consentSuffix}
        </span>
      </label>

      <button
        type="submit"
        className="btn-skew"
        disabled={busy || !agreed}
        style={{
          width: '100%',
          padding: '0 24px',
          height: 52,
          opacity: busy || !agreed ? 0.6 : 1,
        }}
      >
        <span className="btn-skew-label">{busy ? t.searchBusy : t.searchSubmit}</span>
      </button>

      <p
        style={{
          margin: 0,
          padding: '4px 4px 0',
          textAlign: 'center',
          fontSize: 12,
          color: 'var(--mute)',
        }}
      >
        {t.credits}
      </p>
    </form>
  );
}
