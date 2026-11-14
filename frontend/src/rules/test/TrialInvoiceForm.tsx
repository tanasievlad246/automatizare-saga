import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import type { Client, TrialAsk, TrialInvoice, TrialLine } from '../../types'
import { EMPTY, changeLine, hasCodes } from './trialInvoice'

/** Where the trial invoice starts from: one of the four choices the person is given. */
export type StartFrom = 'empty' | 'saved' | 'materiale' | 'combustibil'

/** The trial invoice written out, and the two buttons that put it through the program. */
export function TrialInvoiceForm({
  trial, onChange, clients, asking, onAsk, onStartFrom,
}: {
  trial: TrialInvoice
  onChange: (trial: TrialInvoice) => void
  clients: Client[]
  /** Which question is awaiting its answer, if any. */
  asking: TrialAsk | null
  onAsk: (ask: TrialAsk) => void
  onStartFrom: (start: StartFrom) => void
}) {
  // The codes are rarely there; they stay folded away unless a line has one. They open by
  // themselves when codes arrive (a saved invoice picked); folding them again is the person's choice.
  const withCodes = hasCodes(trial)
  const [codesShown, setCodesShown] = useState(withCodes)
  const [hadCodes, setHadCodes] = useState(withCodes)
  if (withCodes !== hadCodes) {
    setHadCodes(withCodes)
    if (withCodes) setCodesShown(true)
  }
  const set = (changed: Partial<TrialInvoice>) => onChange({ ...trial, ...changed })
  const setLine = (index: number, changed: Partial<TrialLine>) =>
    set({ lines: trial.lines.map((line, at) => (at === index ? changeLine(line, changed) : line)) })
  const removeLine = (index: number) => {
    const rest = trial.lines.filter((_, at) => at !== index)
    set({ lines: rest.length > 0 ? rest : EMPTY.lines })
  }
  const waiting = asking !== null

  return (
    <section aria-label="Factura de probă" className="flex flex-col gap-5 rounded-2xl border bg-card px-6 py-5.5">
      <h2 className="text-2xl">Factura de probă</h2>

      <div className="flex flex-col gap-2">
        <div className="font-bold">Porniți de la</div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => onStartFrom('empty')}>O factură goală</Button>
          <Button variant="outline" disabled={!trial.clientCui} onClick={() => onStartFrom('saved')}>O factură salvată…</Button>
          <Button variant="outline" onClick={() => onStartFrom('materiale')}>Exemplu: materiale</Button>
          <Button variant="outline" onClick={() => onStartFrom('combustibil')}>Exemplu: combustibil</Button>
        </div>
        {!trial.clientCui && <p className="text-[0.9rem] text-muted-foreground">Alegeți întâi clientul.</p>}
      </div>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(14rem,100%),1fr))] gap-4">
        <div className="flex flex-col gap-1.5 [grid-column:1/-1]">
          <Label htmlFor="trial-client">Clientul</Label>
          <NativeSelect
            id="trial-client"
            className="w-full"
            value={trial.clientCui ?? ''}
            onChange={(event) => set({ clientCui: event.target.value || null })}
          >
            <NativeSelectOption value="">Fără client (doar regulile pentru toți clienții)</NativeSelectOption>
            {clients.map((client) => (
              <NativeSelectOption key={client.cui} value={client.cui}>{client.name}</NativeSelectOption>
            ))}
          </NativeSelect>
          <p className="text-[0.9rem] text-muted-foreground">Unele reguli sunt doar pentru un client.</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="trial-supplier">Furnizorul</Label>
          <Input id="trial-supplier" value={trial.supplierName} onChange={(event) => set({ supplierName: event.target.value })} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="trial-supplier-cui">CUI-ul furnizorului</Label>
          <Input id="trial-supplier-cui" inputMode="numeric" value={trial.supplierCui} onChange={(event) => set({ supplierCui: event.target.value })} />
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <div className="hidden grid-cols-[minmax(0,1fr)_6rem_7.5rem_5rem] gap-2.5 font-bold min-[40rem]:grid">
          <span>Ce scrie pe factură</span><span>Cantitate</span><span>Preț fără TVA</span><span />
        </div>
        {trial.lines.map((line, index) => (
          <div key={index} className="flex flex-col gap-2 border-b pb-3 last:border-b-0">
            <div className="grid grid-cols-[minmax(0,1fr)_6rem_7.5rem] gap-2.5 min-[40rem]:grid-cols-[minmax(0,1fr)_6rem_7.5rem_5rem]">
              <Input aria-label="Descriere" placeholder="Ce scrie pe factură" className="col-span-3 min-[40rem]:col-span-1" value={line.description} onChange={(event) => setLine(index, { description: event.target.value })} />
              <Input aria-label="Cantitate" inputMode="decimal" placeholder="Cantitate" value={line.quantity} onChange={(event) => setLine(index, { quantity: event.target.value })} />
              <Input aria-label="Preț fără TVA" inputMode="decimal" placeholder="Preț fără TVA" value={line.unitPrice} onChange={(event) => setLine(index, { unitPrice: event.target.value })} />
              <Button variant="link" onClick={() => removeLine(index)}>Șterge</Button>
            </div>
            {codesShown && (
              <div className="grid grid-cols-[repeat(auto-fit,minmax(min(11rem,100%),1fr))] gap-2.5">
                <Input aria-label="Codul furnizorului" placeholder="Codul furnizorului" value={line.sellerCode} onChange={(event) => setLine(index, { sellerCode: event.target.value })} />
                <Input aria-label="Cod de bare" placeholder="Cod de bare" value={line.barcode} onChange={(event) => setLine(index, { barcode: event.target.value })} />
                <Input aria-label="Coduri CPV sau NC" placeholder="Coduri CPV sau NC, cu virgulă" value={line.commodityCodes} onChange={(event) => setLine(index, { commodityCodes: event.target.value })} />
              </div>
            )}
          </div>
        ))}
        <Button variant="outline" className="self-start" onClick={() => set({ lines: [...trial.lines, ...EMPTY.lines] })}>
          + Adaugă un rând
        </Button>
        {trial.startedFrom && (
          <p className="text-[0.9rem] text-muted-foreground">
            Pornită de la factura {trial.startedFrom}: unitățile, cota de TVA și moneda rămân ca pe acea factură.
          </p>
        )}
      </div>

      <Button variant="link" className="self-start px-0" aria-expanded={codesShown} onClick={() => setCodesShown(!codesShown)}>
        {codesShown ? '⌄' : '›'} Coduri de pe factură (codul furnizorului, cod de bare, cod CPV sau NC)
      </Button>

      <div className="flex flex-wrap gap-2.5">
        <Button size="lg" className="font-bold" disabled={waiting} onClick={() => onAsk('rules_then_jev')}>
          {asking === 'rules_then_jev' ? 'Se caută contul…' : 'Vezi ce cont primește'}
        </Button>
        <Button size="lg" variant="outline" disabled={waiting} onClick={() => onAsk('jev_only')}>
          {asking === 'jev_only' ? 'Este întrebat Jev…' : 'Întreabă-l direct pe Jev'}
        </Button>
      </div>
      <div className="flex flex-col gap-2 text-[0.9rem] text-muted-foreground">
        <p>
          <strong className="text-foreground">„Vezi ce cont primește”</strong> face ce face programul cu o factură adevărată: întâi regulile
          dumneavoastră, iar dacă niciuna nu se potrivește, este întrebat Jev.{' '}
          <strong className="text-foreground">„Întreabă-l direct pe Jev”</strong> sare peste reguli.
        </p>
        <p>Fiecare întrebare pusă lui Jev costă puțin. Costul apare la „Costuri Jev”, ca „probă de reguli”.</p>
      </div>
    </section>
  )
}
