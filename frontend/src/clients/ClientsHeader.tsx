import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { ON_FIRST, allSwitch, headerLine } from './switchedOff'

/**
 * The head of the client list: one check that stands for every client's switch, and how many
 * are on and off. Always about the whole list, whatever a search shows. `onPress`: the check
 * was pressed; nothing changes until the window that follows is answered.
 */
export function ClientsHeader({ on, off, onPress }: { on: number; off: number; onPress: () => void }) {
  const state = allSwitch(on, off)
  return (
    <div className="flex min-h-15 flex-wrap items-center gap-x-5 gap-y-1 rounded-2xl border bg-muted px-5.5 py-2">
      <div className="flex min-h-11 items-center gap-3">
        <Checkbox
          id="all-clients"
          className="size-7 bg-card"
          // A tick: every client is on. A dash: some are. The press asks first, so the check stays as it is.
          checked={state === 'all' ? true : state === 'some' ? 'indeterminate' : false}
          aria-describedby="all-clients-state"
          onCheckedChange={onPress}
        />
        <Label htmlFor="all-clients" className="text-lg font-bold">Toți clienții</Label>
      </div>
      <p id="all-clients-state" className="font-semibold">{headerLine(on, off)}</p>
      {state === 'some' && <p className="text-[0.9rem] text-muted-foreground sm:ml-auto">{ON_FIRST}</p>}
    </div>
  )
}
