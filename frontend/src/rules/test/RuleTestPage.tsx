import { useMutation, useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { Link } from 'react-router'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PageTitle } from '@/components/PageTitle'
import { api } from '../../api'
import type { RuleTestResult, TrialAsk, TrialInvoice } from '../../types'
import { ProposedRuleCardBody } from '../ProposedRuleCardBody'
import { SavedInvoicePicker } from './SavedInvoicePicker'
import { TrialAnswer } from './TrialAnswer'
import { TrialInvoiceForm } from './TrialInvoiceForm'
import type { StartFrom } from './TrialInvoiceForm'
import { EXAMPLES, REFUSED_HERE, fromDocument, hasMore, linesRead, startedFrom, toRequest } from './trialInvoice'

/** A made-up invoice put through the path a real one takes, to see which account it would get. */
export function RuleTestPage() {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients }).data?.clients ?? []
  const [trial, setTrial] = useState<TrialInvoice>(EXAMPLES.materiale)
  // The codes are rarely there, so they stay folded away, but they open by themselves when a
  // start brings some (a saved invoice picked). Folding them again is the person's choice.
  const [moreShown, setMoreShown] = useState(false) // the example the screen opens with has none
  const start = (next: TrialInvoice) => {
    setTrial(next)
    if (hasMore(next)) setMoreShown(true)
  }
  const [choosing, setChoosing] = useState(false)
  // `lines`, `currency` and `clientName` are those of the invoice that was asked about, not of the form as it is now.
  const [answer, setAnswer] = useState<{
    result: RuleTestResult; ask: TrialAsk; number: number; lines: number; currency: string; clientName?: string
  } | null>(null)
  const answers = useRef(0)
  // The proposed rule of one answer is hidden by "Nu acum" or once its rule exists; the next answer brings its own.
  const [proposalHidden, setProposalHidden] = useState(false)

  const ask = useMutation({
    mutationFn: async (how: TrialAsk) => ({
      result: await api.testRules(toRequest(trial, how)), lines: linesRead(trial), currency: trial.currency,
      clientName: clients.find((entry) => entry.cui === trial.clientCui)?.name,
    }),
    onSuccess: ({ result, lines, currency, clientName }, how) => {
      setAnswer({ result, ask: how, number: ++answers.current, lines, currency, clientName })
      setProposalHidden(false)
    },
  })
  const pick = useMutation({
    mutationFn: (invoiceId: string) => api.invoiceView(invoiceId),
    onSuccess: (view) => {
      start(fromDocument(view))
      setChoosing(false)
    },
  })

  const client = clients.find((entry) => entry.cui === trial.clientCui)
  const startFrom = (from: StartFrom) => {
    if (from === 'saved') {
      pick.reset()
      setChoosing(true)
    } else start(startedFrom(from, trial.clientCui))
  }
  const suggestion = answer?.result.suggestion
  // Who chose the account the proposed rule would give: Jev, on the line it comes from.
  const suggestedFrom = answer?.result.lines.find((entry) => entry.line === suggestion?.from_line)
  const chosenByJev = answer?.result.per_line ? suggestedFrom?.decided_by === 'jev' : answer?.result.decided_by === 'jev'

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/reguli" className="font-semibold">‹ Înapoi la reguli</Link>
        <div className="mt-3">
          <PageTitle title="Testează regulile">
            Scrieți o factură de probă și vedeți ce cont primește fiecare linie și de ce, la fel ca o factură venită de la ANAF. Nu se salvează nimic și nimic nu ajunge în SAGA.
          </PageTitle>
        </div>
      </div>

      {/* One column that may shrink below its widest piece (the client list's longest name), so a
          narrow window gets no sideways scroll; two side by side from 72rem. */}
      <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-6 min-[72rem]:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <div className="flex flex-col gap-4">
          <TrialInvoiceForm
            trial={trial}
            onChange={setTrial}
            clients={clients}
            asking={ask.isPending ? ask.variables : null}
            onAsk={(how) => {
              // Nothing of an earlier trial stays on screen while this one is awaited or after it fails.
              setAnswer(null)
              ask.mutate(how)
            }}
            onStartFrom={startFrom}
            moreShown={moreShown}
            onMoreShown={setMoreShown}
          />
          {ask.error && <ErrorNotice error={ask.error} here={REFUSED_HERE} />}
        </div>
        {answer && (
          <div className="flex flex-col gap-4">
            <TrialAnswer
              result={answer.result}
              ask={answer.ask}
              linesOnInvoice={answer.lines}
              clientName={answer.clientName}
              currency={answer.currency}
            />
            {suggestion && !proposalHidden && (
              <ProposedRuleCardBody
                // The card keeps what the person chose (words ticked, what it looks for) in its own
                // state, started from the suggestion. A new answer must start it afresh, not inherit those.
                key={answer.number}
                suggestion={suggestion}
                chosenBy={chosenByJev ? 'jev' : undefined}
                onNotNow={() => setProposalHidden(true)}
                onCreated={() => setProposalHidden(true)}
              />
            )}
          </div>
        )}
      </div>

      {choosing && client && (
        <SavedInvoicePicker
          client={client}
          loading={pick.isPending}
          error={pick.error}
          onPick={(invoiceId) => pick.mutate(invoiceId)}
          onClose={() => setChoosing(false)}
        />
      )}
    </div>
  )
}
