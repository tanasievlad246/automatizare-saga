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
import { EXAMPLES, REFUSED_HERE, fromDocument, startedFrom, toRequest } from './trialInvoice'

/** A made-up invoice put through the path a real one takes, to see which account it would get. */
export function RuleTestPage() {
  const clients = useQuery({ queryKey: ['clients'], queryFn: api.clients }).data?.clients ?? []
  const [trial, setTrial] = useState<TrialInvoice>(EXAMPLES.materiale)
  const [choosing, setChoosing] = useState(false)
  const [answer, setAnswer] = useState<{ result: RuleTestResult; ask: TrialAsk; number: number } | null>(null)
  const answers = useRef(0)
  // The proposed rule of one answer is hidden by "Nu acum" or once its rule exists; the next answer brings its own.
  const [proposalHidden, setProposalHidden] = useState(false)

  const ask = useMutation({
    mutationFn: (how: TrialAsk) => api.testRules(toRequest(trial, how)),
    onSuccess: (result, how) => {
      setAnswer({ result, ask: how, number: ++answers.current })
      setProposalHidden(false)
    },
  })
  const pick = useMutation({
    mutationFn: (invoiceId: string) => api.invoiceView(invoiceId),
    onSuccess: (view) => {
      setTrial(fromDocument(view))
      setChoosing(false)
    },
  })

  const client = clients.find((entry) => entry.cui === trial.clientCui)
  const startFrom = (start: StartFrom) => {
    if (start === 'saved') {
      pick.reset()
      setChoosing(true)
    } else setTrial(startedFrom(start, trial.clientCui))
  }
  const suggestion = answer?.result.suggestion

  return (
    <div className="flex max-w-[72rem] flex-col gap-6">
      <div>
        <Link to="/reguli" className="font-semibold">‹ Înapoi la reguli</Link>
        <div className="mt-3">
          <PageTitle title="Testează regulile">
            Scrieți o factură de probă și vedeți ce cont ar primi, la fel ca o factură venită de la ANAF. Nu se salvează nimic și nimic nu ajunge în SAGA.
          </PageTitle>
        </div>
      </div>

      <div className="grid items-start gap-6 min-[72rem]:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
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
          />
          {ask.error && <ErrorNotice error={ask.error} here={REFUSED_HERE} />}
        </div>
        {answer && (
          <div className="flex flex-col gap-4">
            <TrialAnswer result={answer.result} ask={answer.ask} />
            {suggestion && !proposalHidden && (
              <ProposedRuleCardBody
                // The card keeps what the person chose (words ticked, what it looks for) in its own
                // state, started from the suggestion. A new answer must start it afresh, not inherit those.
                key={answer.number}
                suggestion={suggestion}
                chosenBy={answer.result.decided_by === 'jev' ? 'jev' : undefined}
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
