import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '../api'
import type { InvoiceKind } from '../types'
import { showError } from '../errorMessages'

/**
 * How sure Jev must be before its answer is used, and the questions it is asked: about one
 * line (clients decided line by line) and about a whole invoice (clients with one account).
 * The questions are those of one kind of invoice; how sure Jev must be is one setting for
 * both, changed with the received ones.
 */
export function JevSettingsCard({
  kind = 'received', minConfidence, question, lineQuestion,
}: { kind?: InvoiceKind; minConfidence: number; question: string; lineQuestion: string }) {
  const issued = kind === 'issued'
  const keys = issued
    ? { line: 'jev_issued_line_instructions', whole: 'jev_issued_instructions' } as const
    : { line: 'jev_line_instructions', whole: 'jev_instructions' } as const
  const queryClient = useQueryClient()
  const [percent, setPercent] = useState(String(Math.round(minConfidence * 100)))
  const [questionShown, setQuestionShown] = useState(false)
  const [typedQuestion, setTypedQuestion] = useState(question)
  const [typedLineQuestion, setTypedLineQuestion] = useState(lineQuestion)
  // An empty field would read as 0%, which lets every answer of Jev's through unchecked.
  const level = percent.trim() === '' ? NaN : Number(percent)
  const levelIsUsable = level >= 0 && level <= 100
  const save = useMutation({
    mutationFn: api.setJevSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      toast.success('Am salvat.')
    },
    onError: showError,
  })

  return (
    <section className="flex flex-col gap-3.5">
      <h2 className="text-2xl">{issued ? 'Întrebările puse lui Jev pentru facturile emise' : 'Cât de sigur trebuie să fie Jev'}</h2>
      <div className="flex flex-col gap-3.5 rounded-2xl border bg-card p-5">
        {issued ? (
          <p className="text-muted-foreground">
            Cât de sigur trebuie să fie Jev este aceeași setare pentru facturile primite și cele emise: acum cel
            puțin {Math.round(minConfidence * 100)}%. O schimbați la fila „Pentru facturile primite”.
          </p>
        ) : (
        <>
        <form
          className="flex flex-wrap items-center gap-x-3.5 gap-y-2.5"
          onSubmit={(event) => {
            event.preventDefault()
            if (levelIsUsable) save.mutate({ min_confidence: level / 100 })
          }}
        >
          <Label htmlFor="min-confidence">Cel puțin</Label>
          <Input
            id="min-confidence"
            type="number"
            min={0}
            max={100}
            value={percent}
            onChange={(event) => setPercent(event.target.value)}
            className="w-24 text-xl font-bold"
          />
          <span className="font-semibold">%</span>
          <Button type="submit" variant="outline" disabled={!levelIsUsable || save.isPending}>Salvează</Button>
        </form>
        <p className="text-muted-foreground">
          Dacă Jev este mai puțin sigur de atât, factura vine la dumneavoastră pentru verificare.
        </p>
        </>
        )}
        {questionShown ? (
          <>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`jev-line-question-${kind}`}>Întrebarea pe care o primește Jev la fiecare linie</Label>
              <p className="text-[0.95rem] text-muted-foreground">Pentru clienții cu clasificarea pe fiecare linie.</p>
              <Textarea id={`jev-line-question-${kind}`} rows={5} value={typedLineQuestion} onChange={(event) => setTypedLineQuestion(event.target.value)} />
              <Button
                variant="outline"
                className="self-start"
                disabled={!typedLineQuestion.trim() || save.isPending}
                onClick={() => save.mutate({ [keys.line]: typedLineQuestion })}
              >
                Salvează întrebarea pentru linie
              </Button>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor={`jev-question-${kind}`}>Întrebarea pe care o primește Jev la fiecare factură</Label>
              <p className="text-[0.95rem] text-muted-foreground">Pentru clienții cu un singur cont pe factură.</p>
              <Textarea id={`jev-question-${kind}`} rows={5} value={typedQuestion} onChange={(event) => setTypedQuestion(event.target.value)} />
              <Button
                variant="outline"
                className="self-start"
                disabled={!typedQuestion.trim() || save.isPending}
                onClick={() => save.mutate({ [keys.whole]: typedQuestion })}
              >
                Salvează întrebarea pentru factură
              </Button>
            </div>
          </>
        ) : (
          <Button variant="link" className="self-start px-0" onClick={() => setQuestionShown(true)}>
            Arată întrebările pe care le primește Jev
          </Button>
        )}
      </div>
    </section>
  )
}
