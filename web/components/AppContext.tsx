'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { LOCALE, STRINGS, type Lang, type Strings } from '@/lib/i18n';

const STORE_LANG = 'zgm.lang';

type App = {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: Strings;
};

const Ctx = createContext<App | null>(null);

/**
 * Language for the whole site, applied to <html lang> and remembered in
 * localStorage. The theme is fixed to light, so there is nothing to keep in
 * sync for it; the first paint of the language is handled by the inline
 * script in the layout, so this only has to adopt what it already settled on.
 */
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>('hr');

  useEffect(() => {
    const root = document.documentElement;
    setLangState(root.getAttribute('lang') === 'en' ? 'en' : 'hr');
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

  const value = useMemo<App>(() => ({ lang, setLang, t: STRINGS[lang] }), [lang, setLang]);

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
