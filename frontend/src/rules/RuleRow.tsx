import { ArrowRight, ChevronDown, ChevronUp } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { Rule } from '../types'

// How each kind of condition reads inside the sentence "Dacă …".
const CONDITIONS: [keyof Rule & ('keywords' | 'supplier_cuis' | 'item_codes' | 'commodity_prefixes'), string][] = [
  ['keywords', 'pe factură scrie'],
  ['supplier_cuis', 'furnizorul are CUI'],
  ['item_codes', 'codul articolului este'],
  ['commodity_prefixes', 'codul CPV sau NC începe cu'],
]

/** One rule, read as a sentence: if this is on the invoice, then that account. */
export function RuleRow({
  rule, position, clientName, onEdit, onMove,
}: { rule: Rule; position: number; clientName: string | null; onEdit: () => void; onMove: (up: boolean) => void }) {
  const conditions = CONDITIONS.filter(([field]) => rule[field].length > 0)
    .map(([field, words]) => `${words}: ${rule[field].join(', ')}`)
    .join(' sau ')

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-2xl border bg-card px-5 py-4">
      <div aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-background font-bold">
        {position}
      </div>
      <div className="min-w-0 flex-[1_1_360px]">
        <p className="text-lg">Dacă <strong>{conditions}</strong></p>
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <ArrowRight aria-hidden className="size-5.5" />
          contul <span className="font-heading text-2xl font-bold">{rule.cont}</span>
          <span className="text-muted-foreground">
            · {rule.client_cui ? `doar pentru ${clientName ?? `CUI ${rule.client_cui}`}` : 'pentru toți clienții'}
          </span>
          {!rule.enabled && <Badge className="bg-muted text-foreground">Oprită</Badge>}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="icon" aria-label={`Mută regula ${rule.name} mai sus`} onClick={() => onMove(true)}>
          <ChevronUp aria-hidden />
        </Button>
        <Button variant="outline" size="icon" aria-label={`Mută regula ${rule.name} mai jos`} onClick={() => onMove(false)}>
          <ChevronDown aria-hidden />
        </Button>
        <Button variant="outline" onClick={onEdit}>Modifică</Button>
      </div>
    </div>
  )
}
