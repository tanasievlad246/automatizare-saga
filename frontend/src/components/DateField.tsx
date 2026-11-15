import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

/** A day chosen from the browser's own calendar, with its name above it. The value is written "2026-11-13". */
export function DateField({
  id, label, value, min, max, onChange,
}: { id: string; label: string; value: string; min?: string; max?: string; onChange: (day: string) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type="date" value={value} min={min} max={max} onChange={(event) => onChange(event.target.value)} className="w-auto" />
    </div>
  )
}
