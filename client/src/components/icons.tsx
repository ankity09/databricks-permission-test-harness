/**
 * Minimal inline-SVG icon set (stroke-based, currentColor). Kept local so the
 * app carries no icon-library dependency and every glyph matches the
 * instrument aesthetic (1.5px hairline strokes).
 */
interface IconProps {
  className?: string
}

const base = 'h-5 w-5'

export function HomeIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? base} aria-hidden="true">
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9.5" />
      <path d="M9.5 21v-6h5v6" />
    </svg>
  )
}

export function TestIcon({ className }: IconProps) {
  // a flask / probe
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? base} aria-hidden="true">
      <path d="M9 3h6" />
      <path d="M10 3v6l-5 9a1.5 1.5 0 0 0 1.3 2.2h11.4A1.5 1.5 0 0 0 19 18l-5-9V3" />
      <path d="M7.5 15h9" />
    </svg>
  )
}

export function ScenariosIcon({ className }: IconProps) {
  // a matrix / grid
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? base} aria-hidden="true">
      <rect x="3" y="3" width="7" height="7" rx="1.2" />
      <rect x="14" y="3" width="7" height="7" rx="1.2" />
      <rect x="3" y="14" width="7" height="7" rx="1.2" />
      <path d="M14.5 17.5 17 20l4-4.5" />
    </svg>
  )
}

export function ActivityIcon({ className }: IconProps) {
  // a pulse line
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? base} aria-hidden="true">
      <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />
    </svg>
  )
}

export function SunIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? 'h-4 w-4'} aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  )
}

export function MoonIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? 'h-4 w-4'} aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
    </svg>
  )
}

export function SearchIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className ?? 'h-4 w-4'} aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.2-3.2" />
    </svg>
  )
}

export function ChevronIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" className={className ?? 'h-3.5 w-3.5'} aria-hidden="true">
      <path d="m9 6 6 6-6 6" />
    </svg>
  )
}

/**
 * A tiny glyph per Unity Catalog securable type. Kept intentionally simple so
 * the tree reads at a glance without a heavy icon set.
 */
export function NodeGlyph({ type, className }: IconProps & { type: string }) {
  const c = className ?? 'h-3.5 w-3.5'
  const common = { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: '1.6', strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, className: c, 'aria-hidden': true }
  switch (type) {
    case 'catalog':
      return (
        <svg {...common}>
          <path d="M4 7c0-1.1 3.6-2 8-2s8 .9 8 2-3.6 2-8 2-8-.9-8-2Z" />
          <path d="M4 7v10c0 1.1 3.6 2 8 2s8-.9 8-2V7" />
          <path d="M4 12c0 1.1 3.6 2 8 2s8-.9 8-2" />
        </svg>
      )
    case 'schema':
      return (
        <svg {...common}>
          <rect x="4" y="4" width="16" height="16" rx="2" />
          <path d="M4 9h16M9 9v11" />
        </svg>
      )
    case 'view':
      return (
        <svg {...common}>
          <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6Z" />
          <circle cx="12" cy="12" r="2.5" />
        </svg>
      )
    case 'volume':
      return (
        <svg {...common}>
          <path d="M3 6h18l-2 13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1L3 6Z" />
          <path d="M3 6l2-2h14l2 2" />
        </svg>
      )
    case 'function':
      return (
        <svg {...common}>
          <path d="M8 4h-1a2 2 0 0 0-2 2v3l-2 3 2 3v3a2 2 0 0 0 2 2h1" />
          <path d="M16 4h1a2 2 0 0 1 2 2v3l2 3-2 3v3a2 2 0 0 1-2 2h-1" />
        </svg>
      )
    default: // table
      return (
        <svg {...common}>
          <rect x="3" y="4" width="18" height="16" rx="2" />
          <path d="M3 10h18M9 4v16" />
        </svg>
      )
  }
}
