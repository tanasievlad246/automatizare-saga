import { Check, TriangleAlert } from 'lucide-react'
import { Notice } from '@/components/Notice'
import { cn } from '@/lib/utils'
import type { RuleEvidence } from '../types'
import { describeEvidence } from './ruleEvidence'

/**
 * Under a proposed rule: how it would have done on recent invoices. Green when they are all
 * on the account the rule would give, orange when some are not.
 */
export function RuleEvidenceLine({
  evidence, cont, days, boxed = false,
}: { evidence: RuleEvidence; cont: string; days: number; boxed?: boolean }) {
  const { text, tone } = describeEvidence(evidence, cont, days)
  if (tone === 'none') return <p className="text-muted-foreground">{text}</p>

  const agrees = tone === 'agrees'
  const sentence = agrees ? text : `${text} Verificați înainte de a o crea.`
  if (boxed) return <Notice tone={agrees ? 'done' : 'attention'} className="font-semibold">{sentence}</Notice>

  const Icon = agrees ? Check : TriangleAlert
  return (
    <p className={cn('flex items-start gap-2 font-semibold', agrees ? 'text-done-foreground' : 'text-attention-foreground')}>
      <Icon aria-hidden className="mt-0.5 size-5 shrink-0" />
      {sentence}
    </p>
  )
}
