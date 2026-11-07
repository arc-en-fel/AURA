// Utility functions for formatting numbers safely across the application.
// Returns a localized string for valid numbers, otherwise a placeholder '—'.
export function formatNumber(value?: number | null, locale: string = 'en-US', options?: Intl.NumberFormatOptions): string {
  if (value === undefined || value === null) return '—';
  if (typeof value !== 'number' || !isFinite(value)) return '—';
  return new Intl.NumberFormat(locale, options).format(value);
}

