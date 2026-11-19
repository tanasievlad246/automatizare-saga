import { importedSteps } from './decideAgainTexts'

/** On an invoice imported in SAGA, whose account no longer changes here: how to change it all the same. */
export function ImportedSteps({ perLine }: { perLine: boolean }) {
  const { intro, steps } = importedSteps(perLine)
  return (
    <div className="flex flex-col gap-1.5 rounded-xl bg-background px-4 py-3.5">
      <p className="font-semibold">{intro}</p>
      <ol className="list-decimal pl-5">
        {steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
    </div>
  )
}
