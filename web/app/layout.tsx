import type { Metadata, Viewport } from 'next';
import { AppProvider } from '@/components/AppContext';
import { STRINGS } from '@/lib/i18n';
import { BRAND_APPLE_ICON, BRAND_ICON } from '@/lib/config';
import { EVENT } from '@/lib/event';
import './globals.css';

export const metadata: Metadata = {
  title: STRINGS.hr.metaTitle,
  description: STRINGS.hr.metaDescription,
  icons: BRAND_ICON
    ? {
        icon: [{ url: BRAND_ICON, type: BRAND_ICON.endsWith('.png') ? 'image/png' : 'image/jpeg' }],
        // A square icon suits the home screen better than a wide logo.
        apple: [{ url: BRAND_APPLE_ICON || BRAND_ICON }],
      }
    : undefined,
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

/**
 * Runs before the first paint: applies the remembered language to <html> so
 * an English reader never sees Croatian flash past. The theme is fixed to
 * light — there is no dark mode to restore.
 */
const BOOT = `(function(){try{
var l=localStorage.getItem('zgm.lang');
if(l==='en'||l==='hr'){document.documentElement.setAttribute('lang',l);}
}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="hr" data-theme="light" data-event={EVENT.theme || undefined} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body>
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
