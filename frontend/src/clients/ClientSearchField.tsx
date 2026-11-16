import { Search } from 'lucide-react'
import type { Ref } from 'react'
import { Input } from '@/components/ui/input'

/** The field that narrows the client list by name or CUI, as it is typed. */
export function ClientSearchField({ value, onChange, ref }: { value: string; onChange: (typed: string) => void; ref?: Ref<HTMLInputElement> }) {
  return (
    <div role="search" className="relative max-w-[32.5rem]">
      <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3.5 size-5.5 -translate-y-1/2 text-muted-foreground" />
      <Input
        ref={ref}
        type="search"
        aria-label="Caută un client după nume sau CUI"
        placeholder="Caută după nume sau CUI"
        // The browser's remembered words would open over the list that is being narrowed.
        autoComplete="off"
        className="h-13 pl-11.5 text-lg"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
