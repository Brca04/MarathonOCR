import type { Metadata, Viewport } from 'next';
import { AppProvider } from '@/components/AppContext';
import { STRINGS } from '@/lib/i18n';
import { BRAND_ICON, BRAND_MARK } from '@/lib/config';
import './globals.css';

export const metadata: Metadata = {
  title: STRINGS.hr.metaTitle,
  description: STRINGS.hr.metaDescription,
  icons: {
    icon: [{ url: BRAND_ICON, sizes: '150x150', type: 'image/jpeg' }],
    apple: [{ url: BRAND_MARK }],
  },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
};

/**
 * Runs before the first paint: applies the remembered theme and language to
 * <html> so a light-mode reader never sees a dark flash, and an English reader
 * never sees Croatian. Falls back to the system colour scheme, then to dark.
 */
const BOOT = `(function(){try{
var d=document.documentElement;
var t=localStorage.getItem('zgm.theme');
if(t!=='light'&&t!=='dark'){t=window.matchMedia('(prefers-color-scheme: light)').matches?'light':'dark';}
d.setAttribute('data-theme',t);
var l=localStorage.getItem('zgm.lang');
if(l==='en'||l==='hr'){d.setAttribute('lang',l);}
}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="hr" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body>
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
