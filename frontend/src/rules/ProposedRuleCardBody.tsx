import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { RuleSuggestion } from '../types'
import { reloadWhatARuleChanges, ruleFromProposal } from './proposedRule'
import type { Proposal } from './proposedRule'
import { RuleDialog } from './RuleDialog'
import { RuleEvidenceLine } from './RuleEvidenceLine'

type LooksFor = 'words' | 'supplier'

/**
 * The rule that would have chosen an account no rule chose: the person picks what it looks for
 * (words of the largest line, or the supplier) and creates it. It knows no saved invoice, so
 * what "Nu acum" does is the caller's: remember the refusal, or only hide the card.
 * `chosenBy` says who chose the account, when that is known; `onCreated` is for a caller that
 * must stop showing the card once its rule exists, made by "Creează regula" or saved from
 * "Modifică regula întâi".
 */
export function ProposedRuleCardBody({
  suggestion, onNotNow, chosenBy, onCreated,
}: {
  suggestion: RuleSuggestion
  onNotNow: () => void | Promise<unknown>
  chosenBy?: 'jev' | 'person'
  onCreated?: () => void
}) {
  const queryClient = useQueryClient()
  const { cont, words, supplier_cui: supplierCui } = suggestion
  const supplier = suggestion.supplier_name ?? `furnizorul cu CUI ${supplierCui}`
  const [looksFor, setLooksFor] = useState<LooksFor>(suggestion.ticked.length > 0 || !supplierCui ? 'words' : 'supplier')
  const [ticked, setTicked] = useState(suggestion.ticked)
  const [changing, setChanging] = useState(false)
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients, enabled: changing }).data?.clients ?? []

  const proposal: Proposal = {
    cont,
    keywords: looksFor === 'words' ? words.filter((word) => ticked.includes(word)) : [],
    supplier_cuis: looksFor === 'supplier' && supplierCui ? [supplierCui] : [],
    supplier_name: suggestion.supplier_name,
  }
  const looksForSomething = proposal.keywords.length + proposal.supplier_cuis.length > 0
  const evidence = useQuery({
    queryKey: ['rule-evidence', proposal.keywords, proposal.supplier_cuis],
    queryFn: () => api.tryRule({ keywords: proposal.keywords, supplier_cuis: proposal.supplier_cuis }),
    enabled: looksForSomething,
    placeholderData: keepPreviousData, // the line stays while the next answer is on its way
  }).data

  // Both actions stay busy until the invoice has been read again and this card is gone.
  const reload = () => reloadWhatARuleChanges(queryClient)
  const create = useMutation({
    mutationFn: () => api.addRule(ruleFromProposal(proposal)),
    onSuccess: () => {
      toast.success(`Regula a fost creată. De acum înainte, facturile ca aceasta primesc singure contul ${cont}.`)
      onCreated?.()
      return reload()
    },
    onError: showError,
  })
  const [leaving, setLeaving] = useState(false)
  const busy = create.isPending || leaving
  const notNow = () => {
    setLeaving(true)
    Promise.resolve(onNotNow()).finally(() => setLeaving(false))
  }

  return (
    <section aria-label="Regulă propusă" className="overflow-hidden rounded-2xl border-2 border-primary/40 bg-card">
      <h2 className="bg-fresh px-5 py-3.5 font-sans text-xl font-bold text-fresh-foreground">
        Vreți o regulă pentru facturi ca aceasta?
      </h2>
      <div className="flex flex-col gap-3.5 px-5 pt-4.5 pb-5.5">
        <p>
          Nicio regulă nu s-a potrivit
          {chosenBy ? `, de aceea contul l-${chosenBy === 'jev' ? 'a ales Jev' : 'ați ales dumneavoastră'}` : ''}.
          Cu o regulă, data viitoare contul <strong>{cont}</strong> se pune singur.
        </p>

        {words.length > 0 && supplierCui ? (
          <div className="flex flex-col gap-2">
            <div className="font-bold">Regula să se potrivească dacă:</div>
            <Choice chosen={looksFor === 'words'} onChoose={() => setLooksFor('words')}>
              pe factură apar anumite cuvinte
            </Choice>
            <Choice chosen={looksFor === 'supplier'} onChoose={() => setLooksFor('supplier')}>
              factura este de la {supplier}
            </Choice>
          </div>
        ) : (
          looksFor === 'supplier' && <p className="font-bold">Regula se potrivește dacă factura este de la {supplier}.</p>
        )}

        {looksFor === 'words' && (
          <div className="flex flex-col gap-2">
            <div className="font-bold">Cuvintele căutate</div>
            <div className="flex flex-wrap gap-2">
              {words.map((word) => (
                <WordToTick
                  key={word}
                  word={word}
                  ticked={ticked.includes(word)}
                  onToggle={() => setTicked(ticked.includes(word) ? ticked.filter((other) => other !== word) : [...ticked, word])}
                />
              ))}
            </div>
            <p className="text-[0.9rem] text-muted-foreground">
              Regula se potrivește dacă apare oricare dintre cuvintele bifate. Sunt de pe{' '}
              {suggestion.from_line != null ? `linia ${suggestion.from_line}` : 'linia cu valoarea cea mai mare'} a facturii: „{suggestion.line}”.
            </p>
          </div>
        )}

        {!looksForSomething && <p className="font-semibold text-attention-foreground">Bifați cel puțin un cuvânt.</p>}
        {looksForSomething && evidence && <RuleEvidenceLine evidence={evidence} cont={cont} days={evidence.days} boxed />}

        <div className="flex flex-wrap gap-2.5">
          <Button size="lg" className="font-bold" disabled={!looksForSomething || busy} onClick={() => create.mutate()}>
            Creează regula
          </Button>
          <Button size="lg" variant="outline" disabled={busy} onClick={notNow}>Nu acum</Button>
        </div>
        <Button variant="link" className="self-start px-0" onClick={() => setChanging(true)}>
          Modifică regula întâi
        </Button>
      </div>
      {changing && (
        <RuleDialog rule="new" draft={ruleFromProposal(proposal)} clients={clients} onClose={() => setChanging(false)} onSaved={onCreated} />
      )}
    </section>
  )
}

/** One of the two things the rule can look for. The chosen one is filled and says so to a screen reader. */
function Choice({ chosen, onChoose, children }: { chosen: boolean; onChoose: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={chosen}
      onClick={onChoose}
      className={cn(
        'min-h-12 cursor-pointer rounded-lg border-2 px-4 py-2 text-left',
        'flex items-center gap-2.5',
        chosen ? 'border-primary bg-fresh font-bold text-fresh-foreground' : 'border-input bg-card font-semibold hover:bg-muted',
      )}
    >
      {/* The tick says which one is chosen; the tint alone is too faint a difference. */}
      {chosen ? <Check aria-hidden className="size-5 shrink-0" strokeWidth={2.6} /> : <span aria-hidden className="size-5 shrink-0" />}
      {children}
    </button>
  )
}

function WordToTick({ word, ticked, onToggle }: { word: string; ticked: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={ticked}
      onClick={onToggle}
      className={cn(
        'flex min-h-11 cursor-pointer items-center gap-2 rounded-full border-2 px-4',
        ticked ? 'border-secondary bg-secondary font-bold text-secondary-foreground' : 'border-input bg-card font-semibold hover:bg-muted',
      )}
    >
      {ticked && <Check aria-hidden className="size-4.5" strokeWidth={2.6} />}
      {word}
    </button>
  )
}
