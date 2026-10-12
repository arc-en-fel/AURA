/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        aura: {
          navy: '#0B1F3A',         // Primary Navy Blue
          deep: '#123B63',         // Secondary Deep Blue
          cyan: '#00B8D9',         // Accent Cyan Blue
          'cyan-hover': '#009bb8',
          yellow: '#FFC928',       // Highlight Yellow
          charcoal: '#1F2937',     // Text Dark Charcoal
          green: '#22C55E',        // Success Green
          surface: '#F8FAFC',
          card: '#FFFFFF',
          border: '#E2E8F0',
          muted: '#64748B',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      boxShadow: {
        'subtle': '0 1px 3px 0 rgba(11, 31, 58, 0.05), 0 1px 2px 0 rgba(11, 31, 58, 0.03)',
        'card': '0 4px 6px -1px rgba(11, 31, 58, 0.06), 0 2px 4px -1px rgba(11, 31, 58, 0.03)',
        'elevated': '0 10px 15px -3px rgba(11, 31, 58, 0.08), 0 4px 6px -2px rgba(11, 31, 58, 0.04)',
        'glow-cyan': '0 0 15px rgba(0, 184, 217, 0.35)',
      },
    },
  },
  plugins: [],
}
