interface NegativeTestToggleProps {
  value: boolean
  onChange: (v: boolean) => void
}

export function NegativeTestToggle({ value, onChange }: NegativeTestToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={value}
      onClick={() => onChange(!value)}
      className="group flex items-center gap-3 rounded-md border border-line bg-surface px-3 py-2 text-left focus:outline-none focus-visible:ring-1 focus-visible:ring-lava"
    >
      <span
        className={
          'relative h-5 w-9 shrink-0 rounded-full transition-colors ' +
          (value ? 'bg-lava' : 'bg-line')
        }
      >
        <span
          className={
            'absolute top-0.5 h-4 w-4 rounded-full bg-ink transition-transform ' +
            (value ? 'translate-x-4' : 'translate-x-0.5')
          }
        />
      </span>
      <span>
        <span className="block text-sm font-medium text-ink">Negative test</span>
        <span className="block font-mono text-[11px] text-ink-faint">
          expected denial counts as a pass
        </span>
      </span>
    </button>
  )
}
