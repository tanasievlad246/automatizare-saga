import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import type { Client, Rule, RuleFields } from '../types'
import { reloadWhatARuleChanges } from './proposedRule'

const EMPTY: RuleFields = {
  name: '', cont: '', keywords: [], supplier_cuis: [], item_codes: [], commodity_prefixes: [],
  client_cui: null, enabled: true,
}

/**
 * Writing a rule, or changing one. Lists are typed with commas between the entries.
 * A new rule can start from a `draft`, such as a proposed rule the person wants to adjust.
 */
export function RuleDialog({
  rule, draft, clients, onClose,
}: { rule: Rule | 'new'; draft?: RuleFields; clients: Client[]; onClose: () => void }) {
  const queryClient = useQueryClient()
  const existing = rule === 'new' ? null : rule
  const [fields, setFields] = useState<RuleFields>(existing ?? draft ?? EMPTY)
  const set = (changed: Partial<RuleFields>) => setFields({ ...fields, ...changed })
  // The two code conditions are rarely needed; they stay folded away unless the rule uses them.
  const [codesShown, setCodesShown] = useState(fields.item_codes.length + fields.commodity_prefixes.length > 0)

  const afterChange = {
    onSuccess: () => {
      reloadWhatARuleChanges(queryClient)
      onClose()
    },
  }
  const save = useMutation({
    mutationFn: () => (existing ? api.changeRule(existing.id, fields) : api.addRule(fields)),
    ...afterChange,
  })
  const remove = useMutation({ mutationFn: () => api.deleteRule(existing!.id), ...afterChange })

  return (
    <Dialog open onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="font-heading text-3xl">{existing ? 'Modifică regula' : 'Adaugă o regulă'}</DialogTitle>
          <DialogDescription className="text-lg">
            Regula se potrivește dacă măcar una dintre condiții este adevărată pentru linia cu valoarea cea mai
            mare a facturii.
          </DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate()
          }}
        >
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(220px,100%),1fr))] gap-4">
            <Field id="rule-name" label="Numele regulii">
              <Input id="rule-name" value={fields.name} onChange={(event) => set({ name: event.target.value })} />
            </Field>
            <Field id="rule-cont" label="Contul">
              <Input id="rule-cont" placeholder="de exemplu 6022" value={fields.cont} onChange={(event) => set({ cont: event.target.value })} />
            </Field>
          </div>
          <ListField
            id="rule-keywords"
            label="Cuvinte de pe factură"
            hint="Despărțiți-le prin virgulă. Un * la sfârșit înseamnă orice terminație: transport*"
            entries={fields.keywords}
            onChange={(keywords) => set({ keywords })}
          />
          <ListField
            id="rule-suppliers"
            label="CUI-ul furnizorului"
            hint="Toate facturile de la acești furnizori primesc contul."
            entries={fields.supplier_cuis}
            onChange={(supplier_cuis) => set({ supplier_cuis })}
          />
          {codesShown ? (
            <>
              <ListField id="rule-item-codes" label="Codul articolului la furnizor" entries={fields.item_codes} onChange={(item_codes) => set({ item_codes })} />
              <ListField id="rule-commodity" label="Începutul codului CPV sau NC" entries={fields.commodity_prefixes} onChange={(commodity_prefixes) => set({ commodity_prefixes })} />
            </>
          ) : (
            <Button type="button" variant="link" className="self-start px-0" onClick={() => setCodesShown(true)}>
              Arată și condițiile după coduri
            </Button>
          )}
          <Field id="rule-client" label="Pentru cine este regula">
            <NativeSelect
              id="rule-client"
              className="w-full"
              value={fields.client_cui ?? ''}
              onChange={(event) => set({ client_cui: event.target.value || null })}
            >
              <NativeSelectOption value="">Pentru toți clienții</NativeSelectOption>
              {clients.map((client) => (
                <NativeSelectOption key={client.cui} value={client.cui}>Doar pentru {client.name}</NativeSelectOption>
              ))}
            </NativeSelect>
          </Field>
          <div className="flex min-h-12 items-center gap-3">
            <Checkbox id="rule-enabled" checked={fields.enabled} onCheckedChange={(checked) => set({ enabled: checked === true })} />
            <Label htmlFor="rule-enabled">Regula este pornită</Label>
          </div>
          {/* Said here, beside what was typed, not in a message that goes away. */}
          {(save.error ?? remove.error) && <Notice tone="attention">{errorMessage(save.error ?? remove.error)}</Notice>}
          <DialogFooter className="sm:justify-between">
            {existing ? (
              <Button type="button" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                Șterge regula
              </Button>
            ) : <span />}
            <div className="flex flex-wrap gap-2.5">
              <Button type="button" variant="outline" onClick={onClose}>Renunță</Button>
              <Button type="submit" disabled={save.isPending}>Salvează regula</Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {hint && <p className="text-[0.9rem] text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** A list typed as text with commas; what is typed is kept as it is until it is read. */
function ListField({
  id, label, hint, entries, onChange,
}: { id: string; label: string; hint?: string; entries: string[]; onChange: (entries: string[]) => void }) {
  const [text, setText] = useState(entries.join(', '))
  return (
    <Field id={id} label={label} hint={hint}>
      <Input
        id={id}
        value={text}
        onChange={(event) => {
          setText(event.target.value)
          onChange(event.target.value.split(',').map((entry) => entry.trim()).filter(Boolean))
        }}
      />
    </Field>
  )
}
