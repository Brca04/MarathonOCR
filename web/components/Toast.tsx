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
        background: '#f2f5fb',
        color: '#070e1c',
        fontSize: 14,
        fontWeight: 600,
        textAlign: 'center',
        animation: 'rise .3s ease both',
      }}
    >
      {message}
    </div>
  );
}
