import { useEffect, useRef } from 'react'
import anime from 'animejs'
import { usePrefersReducedMotion } from '../../hooks/useReducedMotion'

interface CountUpProps {
  value: number
  /** ms */
  duration?: number
  className?: string
}

/**
 * Animates a number from 0 to `value` using anime.js. Respects reduced-motion
 * (renders the final value immediately). Used for the big verdict readouts.
 */
export function CountUp({ value, duration = 500, className }: CountUpProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const reduced = usePrefersReducedMotion()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (reduced) {
      el.textContent = String(value)
      return
    }
    const obj = { n: 0 }
    const anim = anime({
      targets: obj,
      n: value,
      duration,
      easing: 'easeOutCubic',
      round: 1,
      update: () => {
        el.textContent = String(obj.n)
      },
    })
    return () => anim.pause()
  }, [value, duration, reduced])

  return <span ref={ref} className={className}>{value}</span>
}
