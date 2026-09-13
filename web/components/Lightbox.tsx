'use client';

import { useEffect } from 'react';
import { PRICE_SINGLE_EUR } from '@/lib/config';
import type { GalleryPhoto } from '@/lib/types';

export default function Lightbox({
  photos,
  index,
  owned,
  onClose,
  onStep,
  onBuy,
  onDownloadPreview,
  onDownloadOriginal,
}: {
  photos: GalleryPhoto[];
  index: number;
  owned: boolean;
  onClose: () => void;
  onStep: (delta: number) => void;
  onBuy: () => void;
  onDownloadPreview: () => void;
  onDownloadOriginal: () => void;
}) {
  const photo = photos[index];

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowRight') onStep(1);
      if (e.key === 'ArrowLeft') onStep(-1);
    };
    window.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = '';
    };
  }, [onClose, onStep]);

  if (!photo) return null;

  const [rw, rh] = photo.ratio.split('/').map(Number);
  const ratioNum = (rw / rh).toFixed(4);

  const iconBtn: React.CSSProperties = {
    display: 'grid',
    placeItems: 'center',
    border: '1px solid #1c2a45',
    background: 'transparent',
    color: '#f2f5fb',
    borderRadius: '50%',
    width: 44,
    height: 44,
    transition: 'border-color .2s',
  };

  return (
    <div
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Photo viewer"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 100,
        background: 'rgba(7,14,28,.97)',
        display: 'grid',
        gridTemplateRows: 'auto 1fr auto',
        animation: 'fade .2s ease both',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '16px clamp(16px,4vw,48px)',
          fontSize: 13,
          color: '#8b9bba',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--mono)',
            letterSpacing: '.06em',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          <span style={{ color: '#f2f5fb' }}>{index + 1}</span> / {photos.length}{' '}
          <span style={{ color: '#4c5c7c' }}>·</span> {photo.course_point}{' '}
          <span style={{ color: '#4c5c7c' }}>·</span> {photo.clock}
        </span>
        <button onClick={onClose} aria-label="Close" className="btn-outline" style={iconBtn}>
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div
        style={{
          position: 'relative',
          display: 'grid',
          placeItems: 'center',
          padding: '0 clamp(56px,8vw,120px)',
          minHeight: 0,
        }}
      >
        <button
          onClick={(e) => {
            e.stopPropagation();
            onStep(-1);
          }}
          aria-label="Previous photo"
          className="btn-outline"
          style={{
            ...iconBtn,
            position: 'absolute',
            left: 'clamp(8px,2vw,32px)',
            top: '50%',
            transform: 'translateY(-50%)',
            background: '#070e1c',
            width: 48,
            height: 48,
          }}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>

        <figure
          onClick={(e) => e.stopPropagation()}
          style={{
            margin: 0,
            position: 'relative',
            width: `min(100%, 1200px, calc((100vh - 200px) * ${ratioNum}))`,
            aspectRatio: photo.ratio,
            borderRadius: 8,
            overflow: 'hidden',
            background: '#0e192e',
            boxShadow: 'inset 0 0 0 1px rgba(242,245,251,.08)',
            animation: 'settle .3s cubic-bezier(.2,.7,.2,1) both',
          }}
        >
          <div
            role="img"
            aria-label={photo.hint}
            style={{
              position: 'absolute',
              inset: 0,
              backgroundImage: `url(${photo.src})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
            }}
          />
        </figure>

        <button
          onClick={(e) => {
            e.stopPropagation();
            onStep(1);
          }}
          aria-label="Next photo"
          className="btn-outline"
          style={{
            ...iconBtn,
            position: 'absolute',
            right: 'clamp(8px,2vw,32px)',
            top: '50%',
            transform: 'translateY(-50%)',
            background: '#070e1c',
            width: 48,
            height: 48,
          }}
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="m9 18 6-6-6-6" />
          </svg>
        </button>
      </div>

      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          padding: '16px clamp(16px,4vw,48px) 24px',
        }}
      >
        <div style={{ fontSize: 13, color: '#8b9bba' }}>
          Photo by <span style={{ color: '#f2f5fb' }}>{photo.photographer ?? 'Unknown'}</span> ·{' '}
          {photo.dims}
          {photo.match_kind === 'fuzzy' ? (
            <>
              {' '}
              · <span style={{ color: '#8fb6ff' }}>read as {photo.read_as}</span>
            </>
          ) : null}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {owned ? (
            <button
              onClick={onDownloadOriginal}
              className="btn-white"
              style={{
                border: 0,
                background: '#f2f5fb',
                color: '#070e1c',
                borderRadius: 8,
                padding: '0 20px',
                height: 44,
                fontSize: 14,
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                transition: 'background .2s',
              }}
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 3v12m0 0 5-5m-5 5-5-5M4 21h16" />
              </svg>
              Download original
            </button>
          ) : (
            <>
              <button
                onClick={onDownloadPreview}
                className="btn-outline"
                style={{
                  border: '1px solid #1c2a45',
                  background: 'transparent',
                  color: '#f2f5fb',
                  borderRadius: 8,
                  padding: '0 18px',
                  height: 44,
                  fontSize: 14,
                  transition: 'border-color .2s',
                }}
              >
                Download preview
              </button>
              <button
                onClick={onBuy}
                className="btn-blue"
                style={{
                  border: 0,
                  background: '#3f82ff',
                  color: '#070e1c',
                  borderRadius: 8,
                  padding: '0 20px',
                  height: 44,
                  fontSize: 14,
                  fontWeight: 600,
                  transition: 'background .2s',
                }}
              >
                Buy original · €{PRICE_SINGLE_EUR}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
