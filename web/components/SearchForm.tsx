'use client';

import { raceFromBib } from '@/lib/format';
import { isLive } from '@/lib/supabase';
import { useT } from '@/components/AppContext';

const mono = (size = 10): React.CSSProperties => ({
  fontFamily: 'var(--mono)',
  fontSize: size,
  letterSpacing: '.14em',
  textTransform: 'uppercase',
  color: 'var(--mute)',
});

export type SearchSubmit = { bib: string };

export default function SearchForm({
  bib,
  setBib,
  error,
  busy,
  onSubmit,
  onDemo,
}: {
  bib: string;
  setBib: (v: string) => void;
  error: string;
  busy: boolean;
  onSubmit: (v: SearchSubmit) => void;
  onDemo: () => void;
}) {
  const t = useT();
  const race = raceFromBib(bib, t);

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
      <div style={{ display: 'grid', gap: 8, marginBottom: 10 }}>
        <span style={{ ...mono(11), color: 'var(--blue)' }}>{t.searchEyebrow}</span>
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
            {t.bibLabel}
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

      <button
        type="submit"
        className="btn-solid"
        disabled={busy}
        style={{
          border: 0,
          borderRadius: 8,
          background: 'var(--paper)',
          color: 'var(--ink)',
          fontWeight: 600,
          fontSize: 15,
          padding: '0 24px',
          height: 52,
          transition: 'background .2s',
          opacity: busy ? 0.7 : 1,
        }}
      >
        {busy ? t.searchBusy : t.searchSubmit}
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
            textDecorationColor: 'rgba(var(--mute-rgb),.4)',
          }}
        >
          {t.searchDemo}
        </a>
      ) : null}
    </form>
  );
}
