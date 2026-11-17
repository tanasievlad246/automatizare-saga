import { Search, X } from 'lucide-react'
import { useRef } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { cn } from '@/lib/utils'
import { type ListState, type Order, type Party, orderOptions } from './invoiceList'

/**
 * The fields above a list of invoices: a search by name, CUI or number, the days of the invoice,
 * the account (when `accounts` are given) and the order. Every change goes
 * straight to `onChange`; nothing waits for a button.
 */
export function InvoiceFilters({
  id, state, party, accounts, onChange, className,
}: {
  id: string
  state: ListState
  party: Party
  accounts?: { value: string; label: string }[]
  onChange: (changes: Partial<ListState>) => void
  className?: string
}) {
  // Every field shows what the address holds; the address changes at once (see App), so nothing lags.
  const textField = useRef<HTMLInputElement>(null)

  return (
    <div
      role="search"
      aria-label={party === 'supplier' ? 'Caută și filtrează facturile' : 'Caută și filtrează facturile emise'}
      className={cn('flex flex-wrap items-end gap-x-4 gap-y-3.5', className)}
    >
      <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-1.5">
        <Label htmlFor={`${id}-text`}>Caută</Label>
        <div className="relative">
          <Search aria-hidden className="pointer-events-none absolute top-1/2 left-3 size-5 -translate-y-1/2 text-muted-foreground" />
          <Input
            ref={textField}
            id={`${id}-text`}
            type="text"
            placeholder={party === 'supplier' ? 'Furnizor, CUI sau numărul facturii' : 'Cumpărător, CUI sau numărul facturii'}
            autoComplete="off"
            className="pr-11 pl-10"
            value={state.text}
            onChange={(event) => onChange({ text: event.target.value })}
          />
          {state.text && (
            <button
              type="button"
              aria-label="Golește căutarea"
              className="absolute top-1/2 right-1 flex size-10 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
              onClick={() => {
                onChange({ text: '' })
                // The button goes away with the text: the focus goes back to the field.
                textField.current?.focus()
              }}
            >
              <X aria-hidden className="size-5" />
            </button>
          )}
        </div>
      </div>

      <fieldset className="flex min-w-0 flex-col gap-1.5">
        <legend className="mb-1.5 font-semibold">Data facturii</legend>
        {/* "de la" and "până la" are written beside the fields: an empty date field shows only "zz.ll.aaaa". */}
        <div className="flex flex-wrap items-center gap-2">
          <span aria-hidden className="text-muted-foreground">de la</span>
          <Input
            type="date"
            aria-label="Data facturii, de la"
            className="w-auto"
            value={state.from}
            max={state.until || undefined}
            onChange={(event) => onChange({ from: event.target.value })}
          />
          <span aria-hidden className="text-muted-foreground">până la</span>
          <Input
            type="date"
            aria-label="Data facturii, până la"
            className="w-auto"
            value={state.until}
            min={state.from || undefined}
            onChange={(event) => onChange({ until: event.target.value })}
          />
        </div>
      </fieldset>

      {accounts && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`${id}-cont`}>Cont</Label>
          <NativeSelect id={`${id}-cont`} className="min-w-44 max-w-80" value={state.cont} onChange={(event) => onChange({ cont: event.target.value })}>
            {accounts.map((account) => (
              <NativeSelectOption key={account.value} value={account.value}>{account.label}</NativeSelectOption>
            ))}
          </NativeSelect>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${id}-order`}>Ordinea</Label>
        <NativeSelect id={`${id}-order`} className="min-w-56" value={state.order} onChange={(event) => onChange({ order: event.target.value as Order })}>
          {orderOptions(party).map((order) => (
            <NativeSelectOption key={order.value} value={order.value}>{order.label}</NativeSelectOption>
          ))}
        </NativeSelect>
      </div>
    </div>
  )
}
