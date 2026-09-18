import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import anime from 'animejs'
import { usePrefersReducedMotion } from '../../hooks/useReducedMotion'

interface StaggerListProps {
  /** Bumps to re-run the reveal (e.g. a result id or row count). */
  trigger: unknown
  children: ReactNode
  className?: string
  /** CSS selector for the items to stagger, scoped to this container. */
  itemSelector?: string
}

/**
 * Fades + rises direct children with a capped stagger. Wraps any list/table
 * body. Respects reduced-motion (no-op, children render at rest).
 */
export function StaggerList({
  trigger,
  children,
  className,
  itemSelector = ':scope > *',
}: StaggerListProps) {
  const ref = useRef<HTMLDivElement>(null)
  const reduced = usePrefersReducedMotion()

  useEffect(() => {
    const root = ref.current
    if (!root || reduced) return
    const items = root.querySelectorAll(itemSelector)
    if (items.length === 0) return
    const anim = anime({
      targets: items,
      opacity: [0, 1],
      translateY: [6, 0],
      duration: 320,
      easing: 'easeOutQuad',
      delay: anime.stagger(24, { start: 0 }),
    })
    return () => anim.pause()
  }, [trigger, reduced, itemSelector])

  return (
    <div ref={ref} className={className}>
      {children}
    </div>
  )
}
