import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { formatPercent } from '../format'

const TYPED_BY_HAND = 'altul'

/** Picking an account from the list Jev chooses from, or typing one that is not in it. */
export function AccountChooser({
  accounts, likelihoods, busy, label, takeFocus = false, onChoose,
}: {
  label: string // "Alegeți contul" when the invoice has none, "Alegeți alt cont" when it has
  takeFocus?: boolean // true when a button was just replaced by this list
  accounts: Record<string, string>
  likelihoods: Record<string, number> | null // what Jev thought of each account, when it was asked
  busy: boolean
  onChoose: (cont: string) => void
}) {
  const [picked, setPicked] = useState('')
  const [typed, setTyped] = useState('')
  const cont = picked === TYPED_BY_HAND ? typed.trim() : picked
  // Jev's likeliest guesses first, so the probable answer is at the top of the list.
  const offered = Object.entries(accounts).sort(([a], [b]) => (likelihoods?.[b] ?? 0) - (likelihoods?.[a] ?? 0))

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="other-account">{label}</Label>
      <NativeSelect id="other-account" className="w-full" autoFocus={takeFocus} value={picked} onChange={(event) => setPicked(event.target.value)}>
        <NativeSelectOption value="">Alegeți din listă…</NativeSelectOption>
        {offered.map(([account, description]) => (
          <NativeSelectOption key={account} value={account}>
            {account} — {firstPhrase(description)}
            {likelihoods?.[account] ? ` (Jev: ${formatPercent(likelihoods[account])})` : ''}
          </NativeSelectOption>
        ))}
        <NativeSelectOption value={TYPED_BY_HAND}>Alt cont, îl scriu eu…</NativeSelectOption>
      </NativeSelect>
      {picked === TYPED_BY_HAND && (
        <Input
          aria-label="Contul scris de mână"
          placeholder="de exemplu 371.01"
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
        />
      )}
      <Button variant="outline" className="self-start" disabled={!cont || busy} onClick={() => onChoose(cont)}>
        Folosește acest cont
      </Button>
    </div>
  )
}

/** "Combustibil pentru vehicule" from "Combustibil pentru vehicule: motorină, benzină…". */
export function firstPhrase(description: string | undefined): string {
  return (description ?? '').split(/[:.]/)[0].trim()
}
