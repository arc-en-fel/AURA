import React, { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  /**
   * When true, the modal uses a three-region flex layout:
   *   - fixed header (title + close)
   *   - scrollable body (form fields)
   *   - fixed footer (action buttons)
   *
   * The modal panel is capped at 90dvh so it never overflows the viewport.
   * Use this for any form or multi-field dialog.
   *
   * When false (default), the legacy non-portal variant is used for
   * simple confirmation / message dialogs that don't need inner scrolling.
   */
  scrollable?: boolean;
}

const maxWidthMap: Record<NonNullable<ModalProps['maxWidth']>, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
};

// ---------------------------------------------------------------------------
// Scrollable portal modal — used for Create/Edit Record and any tall form.
// Rendered via createPortal into document.body to escape every stacking
// context (transform, will-change, filter) created by the sidebar/layout.
// ---------------------------------------------------------------------------
const ScrollableModal: React.FC<ModalProps> = ({
  onClose,
  title,
  description,
  children,
  footer,
  maxWidth = 'lg',
}) => {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocus = useRef<Element | null>(null);

  useEffect(() => {
    previousFocus.current = document.activeElement;
    document.body.style.overflow = 'hidden';

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);

    // Defer focus so the DOM is painted
    const t = setTimeout(() => closeButtonRef.current?.focus(), 60);

    return () => {
      clearTimeout(t);
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      // Restore focus
      if (previousFocus.current instanceof HTMLElement) {
        previousFocus.current.focus();
      }
    };
  }, [onClose]);

  const panel = (
    // Full-viewport overlay — position:fixed relative to the *initial containing
    // block* (the viewport) because we mount on document.body, not inside any
    // transformed ancestor.
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
        // Do NOT put overflow:hidden here — it would clip the panel on some
        // browsers. Centering via flex is sufficient.
      }}
    >
      {/* Backdrop — click-outside closes */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: 'rgba(11,31,58,0.65)',
          backdropFilter: 'blur(3px)',
          WebkitBackdropFilter: 'blur(3px)',
        }}
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Modal panel */}
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="drm-modal-title"
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'relative',
          display: 'flex',
          flexDirection: 'column',
          width: '100%',
          maxWidth: maxWidth === 'lg' ? '560px'
            : maxWidth === 'xl' ? '680px'
            : maxWidth === '2xl' ? '800px'
            : maxWidth === 'sm' ? '380px'
            : '460px', // md
          // Cap height so panel never exceeds viewport.
          // dvh (dynamic viewport height) accounts for mobile browser chrome.
          maxHeight: 'calc(100dvh - 32px)',
          minHeight: 0,
          overflow: 'hidden',
          background: '#fff',
          borderRadius: '12px',
          border: '1px solid #e2e8f0',
          boxShadow: '0 25px 50px -12px rgba(11,31,58,0.25)',
        }}
      >
        {/* ── Fixed Header ─────────────────────────────────────────────── */}
        <div
          style={{
            flexShrink: 0,
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            padding: '20px 20px 16px',
            borderBottom: '1px solid #f1f5f9',
            background: 'rgba(248,250,252,0.7)',
          }}
        >
          <div>
            <h3
              id="drm-modal-title"
              style={{ fontSize: '17px', fontWeight: 700, color: '#0B1F3A', margin: 0 }}
            >
              {title}
            </h3>
            {description && (
              <p style={{ marginTop: '4px', fontSize: '11px', color: '#94a3b8' }}>
                {description}
              </p>
            )}
          </div>
          <button
            ref={closeButtonRef}
            onClick={onClose}
            aria-label="Close modal"
            style={{
              flexShrink: 0,
              marginLeft: '12px',
              padding: '6px',
              borderRadius: '8px',
              border: 'none',
              background: 'transparent',
              color: '#94a3b8',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'background 0.15s, color 0.15s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = '#f1f5f9';
              (e.currentTarget as HTMLButtonElement).style.color = '#475569';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
              (e.currentTarget as HTMLButtonElement).style.color = '#94a3b8';
            }}
          >
            <X style={{ width: '18px', height: '18px' }} />
          </button>
        </div>

        {/* ── Scrollable Body ───────────────────────────────────────────── */}
        <div
          style={{
            flex: '1 1 auto',
            minHeight: 0,           // critical: without this flex child won't shrink
            overflowY: 'auto',
            overscrollBehavior: 'contain',
            padding: '20px 24px',
            scrollbarGutter: 'stable',
          }}
        >
          {children}
        </div>

        {/* ── Fixed Footer ─────────────────────────────────────────────── */}
        {footer && (
          <div
            style={{
              flexShrink: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: '8px',
              padding: '12px 20px',
              borderTop: '1px solid #f1f5f9',
              background: 'rgba(248,250,252,0.85)',
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );

  // Mount outside every layout container — escapes all CSS transform stacking contexts.
  return createPortal(panel, document.body);
};

// ---------------------------------------------------------------------------
// Legacy non-portal modal — for simple dialogs that don't need inner scrolling.
// ---------------------------------------------------------------------------
const LegacyModal: React.FC<ModalProps> = ({
  onClose,
  title,
  description,
  children,
  footer,
  maxWidth = 'md',
}) => {
  const closeButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    const t = setTimeout(() => closeButtonRef.current?.focus(), 60);
    return () => {
      clearTimeout(t);
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [onClose]);

  const mwClass = maxWidthMap[maxWidth];

  const panel = (
    <div className="fixed inset-0 z-[9999] overflow-y-auto">
      <div
        className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />
      <div className="flex min-h-full items-center justify-center p-4 text-center sm:p-0">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-title"
          className={`relative transform overflow-hidden rounded-xl bg-white text-left shadow-2xl transition-all sm:my-8 w-full ${mwClass} border border-slate-200 animate-fade-in`}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-start justify-between border-b border-slate-100 p-5 bg-slate-50/50">
            <div>
              <h3 id="modal-title" className="text-lg font-bold text-aura-navy">{title}</h3>
              {description && (
                <p className="mt-1 text-xs text-slate-500">{description}</p>
              )}
            </div>
            <button
              ref={closeButtonRef}
              onClick={onClose}
              className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors"
              aria-label="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="p-6 max-h-[75vh] overflow-y-auto">{children}</div>
          {footer && (
            <div className="flex items-center justify-end gap-3 border-t border-slate-100 bg-slate-50/70 px-6 py-4">
              {footer}
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(panel, document.body);
};

// ---------------------------------------------------------------------------
// Public export — same API as before; callers only need to add scrollable={true}
// ---------------------------------------------------------------------------
export const Modal: React.FC<ModalProps> = (props) => {
  if (!props.isOpen) return null;
  return props.scrollable
    ? <ScrollableModal {...props} />
    : <LegacyModal {...props} />;
};
