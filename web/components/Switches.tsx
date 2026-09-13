'use client';

import { useApp } from '@/components/AppContext';
import type { Lang } from '@/lib/i18n';

/**
 * The language slider in the header: a pill with a knob that slides between
 * the two options, the same shape the old Home / Find nav had. The theme
 * switch that used to sit beside it is gone — the site is light-only now.
 */
export default function Switches() {
  const { lang, setLang, t } = useApp();

  return (
    <div
      className="switch"
      role="group"
      aria-label={t.langLabel}
      style={{ gridTemplateColumns: '1fr 1fr', width: 84 }}
    >
      <span
        className="switch-knob"
        aria-hidden="true"
        style={{ '--knob-x': lang === 'en' ? 'calc(100% + 3px)' : '0px' } as React.CSSProperties}
      />
      {(['hr', 'en'] as Lang[]).map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          aria-pressed={lang === code}
          style={{
            height: 28,
            fontFamily: 'var(--mono)',
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '.08em',
          }}
        >
          {code.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
