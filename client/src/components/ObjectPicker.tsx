import type { Tab } from '../types'

interface ObjectPickerProps {
  tab: Tab
  value: string
  onChange: (v: string) => void
}

export function ObjectPicker({ tab, value, onChange }: ObjectPickerProps) {
  const hint =
    tab === 'uc-data'
      ? 'catalog.schema.object  (e.g. main.sales.orders)'
      : 'numeric id or name  (e.g. job id 482910, warehouse id abc123)'
  const label = tab === 'uc-data' ? 'Securable' : 'Object id'

  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-ink-dim">
        {label}
      </span>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={hint}
        spellCheck={false}
        className="w-full rounded-md border border-line bg-base px-3 py-2.5 font-mono text-sm text-ink placeholder:text-ink-faint focus:border-lava focus:outline-none focus-visible:ring-1 focus-visible:ring-lava"
      />
    </label>
  )
}
