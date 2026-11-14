import { PillTabs } from '@/components/PillTabs'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { AREAS } from './eventTexts'

export type Shown = 'tot' | 'probleme'
export type Period = 'azi' | '7' | '30'
export type JournalChoice = { shown: Shown; details: boolean; area: string; period: Period; text: string }

const WHAT_IS_SHOWN: { value: Shown; label: string }[] = [
  { value: 'tot', label: 'Tot' },
  { value: 'probleme', label: 'Doar problemele' },
]

/** What narrows the journal: problems only, one area, a period, a word. */
export function JournalFilters({ choice, onChange }: { choice: JournalChoice; onChange: (choice: JournalChoice) => void }) {
  const set = (changed: Partial<JournalChoice>) => onChange({ ...choice, ...changed })
  return (
    <div className="flex flex-wrap items-center gap-3">
      <PillTabs label="Ce se arată" options={WHAT_IS_SHOWN} value={choice.shown} onChange={(shown) => set({ shown })} />
      <NativeSelect aria-label="Zona" value={choice.area} onChange={(event) => set({ area: event.target.value })}>
        <NativeSelectOption value="">Toate zonele</NativeSelectOption>
        {AREAS.map(([area, name]) => (
          <NativeSelectOption key={area} value={area}>{name}</NativeSelectOption>
        ))}
      </NativeSelect>
      <NativeSelect aria-label="Perioada" value={choice.period} onChange={(event) => set({ period: event.target.value as Period })}>
        <NativeSelectOption value="azi">Azi</NativeSelectOption>
        <NativeSelectOption value="7">Ultimele 7 zile</NativeSelectOption>
        <NativeSelectOption value="30">Ultimele 30 de zile</NativeSelectOption>
      </NativeSelect>
      {/* It says what can be found: the program looks in its own English lines and in their
          data (names, CUIs, invoice numbers), not in the Romanian sentences of this page. */}
      <Input
        aria-label="Caută un client, un CUI sau un număr de factură"
        placeholder="Caută un client, un CUI sau un număr de factură"
        // Wide enough for those words to be read whole; in a narrow window it takes a row of its own.
        className="min-w-0 flex-[1_1_26rem]"
        value={choice.text}
        onChange={(event) => set({ text: event.target.value })}
      />
      <div className="flex min-h-12 items-center gap-2.5">
        <Checkbox id="journal-details" checked={choice.details} onCheckedChange={(checked) => set({ details: checked === true })} />
        <Label htmlFor="journal-details">Arată și detaliile</Label>
      </div>
    </div>
  )
}
