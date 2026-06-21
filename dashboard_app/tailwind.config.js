/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Deep navy panel system matching the SAR mockup
        base: {
          950: '#070d18',
          900: '#0a1322',
          850: '#0d182b',
          800: '#101e34',
          750: '#13243f',
          700: '#1a2d4d',
          600: '#24395f',
        },
        accent: {
          cyan: '#22d3ee',
          blue: '#3b82f6',
          green: '#22c55e',
          amber: '#f59e0b',
          red: '#ef4444',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -12px rgba(0,0,0,0.6)',
        glow: '0 0 0 1px rgba(34,211,238,0.4), 0 0 20px -4px rgba(34,211,238,0.5)',
      },
      keyframes: {
        pulseRing: {
          '0%': { transform: 'scale(0.8)', opacity: '0.7' },
          '100%': { transform: 'scale(2.2)', opacity: '0' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.35' },
        },
        dash: {
          to: { strokeDashoffset: '-20' },
        },
      },
      animation: {
        pulseRing: 'pulseRing 2s ease-out infinite',
        blink: 'blink 1.4s ease-in-out infinite',
        dash: 'dash 1s linear infinite',
      },
    },
  },
  plugins: [],
}
