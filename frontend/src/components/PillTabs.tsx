import { cn } from '@/lib/utils'

type Option<Value> = { value: Value; label: string }

/** A row of rounded buttons where exactly one is chosen: a filter, a period, a view. */
export function PillTabs<Value extends string | number>({
  options, value, onChange, label,
}: { options: Option<Value>[]; value: Value | null; onChange: (value: Value) => void; label: string }) {
  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          onClick={() => onChange(option.value)}
          className={cn(
            'min-h-12 rounded-full border px-5 font-semibold outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
            option.value === value
              ? 'border-secondary bg-secondary text-secondary-foreground'
              : 'border-input bg-card hover:bg-muted',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}
