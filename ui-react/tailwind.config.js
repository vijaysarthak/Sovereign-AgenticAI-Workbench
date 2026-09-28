/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        sov: {
          bg: '#0a0a0a',
          sidebar: '#0f0f0f',
          card: '#141414',
          'card-hover': '#1a1a1a',
          border: '#1e1e1e',
          'border-light': '#2a2a2a',
          orange: '#f97316',
          'orange-dark': '#ea580c',
          'orange-glow': 'rgba(249, 115, 22, 0.15)',
          green: '#22c55e',
          'green-dim': '#166534',
          red: '#ef4444',
          amber: '#f59e0b',
          blue: '#3b82f6',
          purple: '#a855f7',
          'text-primary': '#f5f5f5',
          'text-secondary': '#888888',
          'text-muted': '#555555',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
};
