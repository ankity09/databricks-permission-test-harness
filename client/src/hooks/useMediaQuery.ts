import { useEffect, useState } from 'react'

/**
 * Hook to detect media query matches (e.g., breakpoint).
 * @param query CSS media query string
 * @returns true if query matches, false otherwise
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    // Initialize with the current match state
    if (typeof window !== 'undefined') {
      return window.matchMedia(query).matches
    }
    return false
  })

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)

    const listener = (e: MediaQueryListEvent) => {
      setMatches(e.matches)
    }

    // Defer initial setup to avoid setState-in-effect
    const timer = window.setTimeout(() => {
      if (mediaQuery.matches !== matches) {
        setMatches(mediaQuery.matches)
      }
      mediaQuery.addEventListener('change', listener)
    }, 0)

    return () => {
      window.clearTimeout(timer)
      mediaQuery.removeEventListener('change', listener)
    }
  }, [query, matches])

  return matches
}
