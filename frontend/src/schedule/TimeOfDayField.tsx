import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'

const twoDigits = (count: number) => Array.from({ length: count }, (_, number) => String(number).padStart(2, '0'))
const HOURS = twoDigits(24)
const MINUTES = twoDigits(60)

/**
 * A time of day chosen from two lists, hours 00 to 23 and minutes 00 to 59. The browser's own time field
 * follows the PC's regional settings and may show AM and PM; this one reads the same on every PC.
 */
export function TimeOfDayField({ name, value, onChange }: { name: string; value: string; onChange: (time: string) => void }) {
  const [hour, minute] = value.split(':')
  return (
    <div role="group" aria-label={name} className="flex items-center gap-2 font-semibold tabular-nums">
      <NativeSelect aria-label={`${name}: ora`} value={hour} onChange={(event) => onChange(`${event.target.value}:${minute}`)}>
        {HOURS.map((each) => <NativeSelectOption key={each} value={each}>{each}</NativeSelectOption>)}
      </NativeSelect>
      <span aria-hidden className="text-xl font-bold">:</span>
      <NativeSelect aria-label={`${name}: minutul`} value={minute} onChange={(event) => onChange(`${hour}:${event.target.value}`)}>
        {MINUTES.map((each) => <NativeSelectOption key={each} value={each}>{each}</NativeSelectOption>)}
      </NativeSelect>
    </div>
  )
}
