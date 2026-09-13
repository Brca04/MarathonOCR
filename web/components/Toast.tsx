'use client';

export default function Toast({ message }: { message: string }) {
  if (!message) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed',
        left: '50%',
        bottom: 28,
        transform: 'translateX(-50%)',
        zIndex: 200,
        maxWidth: 'calc(100vw - 32px)',
        padding: '12px 20px',
        borderRadius: 8,
        background: 'var(--paper)',
        color: 'var(--ink)',
        fontSize: 14,
        fontWeight: 600,
        textAlign: 'center',
      }}
    >
      {message}
    </div>
  );
}
