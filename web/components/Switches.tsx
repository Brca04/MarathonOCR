'use client';

import { useApp } from '@/components/AppContext';
import type { Lang } from '@/lib/i18n';

/**
 * The two sliders in the header. Both are the same control: a pill with a knob
 * that slides between two options, the same shape the old Home / Find nav had.
 */
export default function Switches() {
  const { lang, setLang, theme, setTheme, t } = useApp();
  const dark = theme === 'dark';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div
        className="switch"
        role="group"
        aria-label={t.themeLabel}
        style={{ gridTemplateColumns: '1fr 1fr', width: 76 }}
      >
        <span
          className="switch-knob"
          aria-hidden="true"
          style={{ left: dark ? 'calc(50% + 1.5px)' : 3, width: 'calc(50% - 4.5px)' }}
        />
        <button
          type="button"
          onClick={() => setTheme('light')}
          aria-pressed={!dark}
          aria-label={t.themeLight}
          title={t.themeLight}
          style={{ height: 28 }}
        >
          <Sun />
        </button>
        <button
          type="button"
          onClick={() => setTheme('dark')}
          aria-pressed={dark}
          aria-label={t.themeDark}
          title={t.themeDark}
          style={{ height: 28 }}
        >
          <Moon />
        </button>
      </div>

      <div
        className="switch"
        role="group"
        aria-label={t.langLabel}
        style={{ gridTemplateColumns: '1fr 1fr', width: 84 }}
      >
        <span
          className="switch-knob"
          aria-hidden="true"
          style={{ left: lang === 'en' ? 'calc(50% + 1.5px)' : 3, width: 'calc(50% - 4.5px)' }}
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
    </div>
  );
}

const icon: React.SVGProps<SVGSVGElement> = {
  width: 15,
  height: 15,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
} as React.SVGProps<SVGSVGElement>;

function Sun() {
  return (
    <svg {...icon}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function Moon() {
  return (
    <svg {...icon}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  );
}
