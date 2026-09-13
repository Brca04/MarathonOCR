'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { LOCALE, STRINGS, type Lang, type Strings } from '@/lib/i18n';

export type Theme = 'dark' | 'light';

const STORE_THEME = 'zgm.theme';
const STORE_LANG = 'zgm.lang';

type App = {
  lang: Lang;
  setLang: (l: Lang) => void;
  theme: Theme;
  setTheme: (t: Theme) => void;
  t: Strings;
};

const Ctx = createContext<App | null>(null);

/**
 * Theme and language for the whole site. Both are applied to <html> — the theme
 * as data-theme, which every colour token keys off, the language as lang — and
 * remembered in localStorage. The first paint is handled by the inline script
 * in the layout, so this only has to keep the two in sync afterwards.
 */
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>('hr');
  const [theme, setThemeState] = useState<Theme>('dark');

  // Adopt whatever the pre-paint script already settled on, so a stored choice
  // never flashes past on load.
  useEffect(() => {
    const root = document.documentElement;
    setThemeState(root.getAttribute('data-theme') === 'light' ? 'light' : 'dark');
    setLangState(root.getAttribute('lang') === 'en' ? 'en' : 'hr');
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem(STORE_THEME, next);
    } catch {
      /* private window — the choice just does not outlive the session */
    }
  }, []);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    document.documentElement.setAttribute('lang', next);
    document.title = STRINGS[next].metaTitle;
    document
      .querySelector('meta[name="description"]')
      ?.setAttribute('content', STRINGS[next].metaDescription);
    try {
      localStorage.setItem(STORE_LANG, next);
    } catch {
      /* ignored */
    }
  }, []);

  const value = useMemo<App>(
    () => ({ lang, setLang, theme, setTheme, t: STRINGS[lang] }),
    [lang, setLang, theme, setTheme],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useApp(): App {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useApp must be used inside <AppProvider>');
  return ctx;
}

/** Shorthand for the common case: `const t = useT()`. */
export function useT(): Strings {
  return useApp().t;
}

export { LOCALE };
