/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'rvp-bg':       '#0f1117',
        'rvp-surface':  '#1a1d27',
        'rvp-border':   '#2a2d3a',
        'rvp-primary':  '#6366f1',
        'rvp-success':  '#22c55e',
        'rvp-warning':  '#f59e0b',
        'rvp-error':    '#ef4444',
        'rvp-info':     '#3b82f6',
        'rvp-muted':    '#6b7280',
      },
      fontFamily: { mono: ['JetBrains Mono', 'Fira Code', 'monospace'] },
    },
  },
  plugins: [],
}
