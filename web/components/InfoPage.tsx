'use client';

import Link from 'next/link';
import Nav from '@/components/Nav';
import { useApp } from '@/components/AppContext';

/**
 * Plain reading page for the privacy notice and contact details: the site
 * header, a narrow column of text on the page colour, and a way back home.
 */
export default function InfoPage({
  kicker,
  title,
  children,
}: {
  kicker: string;
  title: string;
  children: React.ReactNode;
}) {
  const { lang } = useApp();
  return (
    <main style={{ minHeight: '100svh', background: 'var(--ink)', color: 'var(--paper)', position: 'relative' }}>
      <div style={{ height: 96, background: 'var(--panel)', borderBottom: '1px solid var(--line)', position: 'relative' }}>
        <Nav />
      </div>
      <article
        data-info-page=""
        style={{ maxWidth: 720, margin: '0 auto', padding: 'clamp(28px,6vw,64px) 20px 80px' }}
      >
        <div
          style={{
            fontFamily: 'var(--mono)',
            fontSize: 11,
            letterSpacing: '.16em',
            textTransform: 'uppercase',
            color: 'var(--blue)',
          }}
        >
          {kicker}
        </div>
        <h1 style={{ fontSize: 'clamp(30px,5vw,44px)', letterSpacing: '-.035em', lineHeight: 1.05, margin: '10px 0 24px' }}>
          {title}
        </h1>
        {children}
        <p style={{ marginTop: 48 }}>
          <Link href="/" className="link-mute" style={{ textDecoration: 'underline', textUnderlineOffset: 3 }}>
            {lang === 'hr' ? '← Natrag na pretragu fotografija' : '← Back to photo search'}
          </Link>
        </p>
      </article>
    </main>
  );
}
