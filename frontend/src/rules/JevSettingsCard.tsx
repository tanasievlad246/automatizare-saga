import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { api } from '../api'
import { showError } from '../errorMessages'

/** How sure Jev must be before its answer is used, and the question it is asked. */
export function JevSettingsCard({ minConfidence, question }: { minConfidence: number; question: string }) {
  const queryClient = useQueryClient()
  const [percent, setPercent] = useState(String(Math.round(minConfidence * 100)))
  const [questionShown, setQuestionShown] = useState(false)
  const [typedQuestion, setTypedQuestion] = useState(question)
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
      <h2 className="text-2xl">Cât de sigur trebuie să fie Jev</h2>
      <div className="flex flex-col gap-3.5 rounded-2xl border bg-card p-5">
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
        {questionShown ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor="jev-question">Întrebarea pe care o primește Jev la fiecare factură</Label>
            <Textarea id="jev-question" rows={5} value={typedQuestion} onChange={(event) => setTypedQuestion(event.target.value)} />
            <Button
              variant="outline"
              className="self-start"
              disabled={!typedQuestion.trim() || save.isPending}
              onClick={() => save.mutate({ jev_instructions: typedQuestion })}
            >
              Salvează întrebarea
            </Button>
          </div>
        ) : (
          <Button variant="link" className="self-start px-0" onClick={() => setQuestionShown(true)}>
            Arată întrebarea pe care o primește Jev
          </Button>
        )}
      </div>
    </section>
  )
}
