import { Badge } from '@/components/ui/badge'
import type { Invoice } from '../types'

/** Where an invoice stands, in words: new or not, and what is left to do with it. */
export function InvoiceStateBadges({ invoice }: { invoice: Invoice }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {invoice.is_new && <Badge className="bg-fresh text-fresh-foreground">Nouă</Badge>}
      <StateBadge invoice={invoice} />
    </div>
  )
}

function StateBadge({ invoice }: { invoice: Invoice }) {
  if (invoice.uploaded_to_accounting) return <Badge className="bg-muted text-foreground">Importată în SAGA</Badge>
  switch (invoice.classification_status) {
    case 'review':
      return <Badge className="bg-attention text-attention-foreground">De verificat</Badge>
    case 'classified':
      return <Badge className="bg-done text-done-foreground">Gata pentru SAGA</Badge>
    case 'pending':
      return <Badge className="bg-muted text-foreground">Așteaptă contul</Badge>
    default:
      return <Badge className="bg-muted text-foreground">Fără cont</Badge>
  }
}
