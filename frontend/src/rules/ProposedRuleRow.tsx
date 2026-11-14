import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowRight } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { showError } from '../errorMessages'
import type { ProposedRule, RuleFields } from '../types'
import { conditionInWords, reloadWhatARuleChanges, ruleFromProposal } from './proposedRule'
import { RuleEvidenceLine } from './RuleEvidenceLine'

/** One proposed rule, read as a sentence, with how it would have done and what to do with it. */
export function ProposedRuleRow({
  proposal, days, onChangeFirst,
}: { proposal: ProposedRule; days: number; onChangeFirst: (draft: RuleFields) => void }) {
  const queryClient = useQueryClient()
  // Both actions stay busy until the list has been read again and this row is gone.
  const reload = () => reloadWhatARuleChanges(queryClient)
  const create = useMutation({
    mutationFn: () => api.addRule(ruleFromProposal(proposal)),
    onSuccess: () => {
      toast.success(`Regula a fost creată. De acum înainte, aceste facturi primesc singure contul ${proposal.cont}.`)
      return reload()
    },
    onError: showError,
  })
  const turnDown = useMutation({
    mutationFn: () => api.turnDownProposal(proposal.invoice_ids),
    onSuccess: reload,
    onError: showError,
  })
  const busy = create.isPending || turnDown.isPending

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-xl bg-card px-5 py-4">
      <div className="flex min-w-0 flex-[1_1_360px] flex-col gap-1.5">
        <p className="text-lg">Dacă <strong>{conditionInWords(proposal)}</strong></p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <ArrowRight aria-hidden className="size-5.5" />
          contul <span className="font-heading text-2xl font-bold">{proposal.cont}</span>
          <span className="text-muted-foreground">· pentru toți clienții</span>
        </p>
        <RuleEvidenceLine evidence={proposal} cont={proposal.cont} days={days} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button disabled={busy} onClick={() => create.mutate()}>Creează regula</Button>
        <Button variant="outline" disabled={busy} onClick={() => onChangeFirst(ruleFromProposal(proposal))}>
          Modifică regula întâi
        </Button>
        <Button variant="link" disabled={busy} onClick={() => turnDown.mutate()}>Nu acum</Button>
      </div>
    </div>
  )
}
