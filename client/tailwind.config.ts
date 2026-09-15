import type { Config } from 'tailwindcss'

// DuBois-flavored theme. Colors are CSS variables (space-separated RGB
// channels) so the `/opacity` utilities (e.g. border-pass/50) keep working and
// the whole palette swaps between dark and light via `data-theme` on <html>.
// Actual channel values live in index.css.
const v = (name: string) => `rgb(var(--c-${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Structural surfaces.
        base: v('base'),
        surface: v('surface'),
        'surface-2': v('surface-2'),
        line: v('line'),
        // DuBois lava red — the ONLY UI accent.
        lava: v('lava'),
        'lava-dim': v('lava-dim'),
        // Semantic status.
        pass: v('pass'),
        fail: v('fail'),
        warn: v('warn'),
        // Text.
        ink: v('ink'),
        'ink-dim': v('ink-dim'),
        'ink-faint': v('ink-faint'),
      },
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
    },
  },
  plugins: [],
} satisfies Config
