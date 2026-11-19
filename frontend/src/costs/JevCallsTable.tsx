import { Link } from 'react-router'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { formatPercent, formatUsd, formatUsdExact, formatWhen } from '../format'
import { isIssued } from '../invoices/issuedInvoices'
import type { JevCall } from '../types'

/** Each question put to Jev: when, about which invoice, what it answered and what that cost. */
export function JevCallsTable({ calls, loading }: { calls: JevCall[]; loading: boolean }) {
  if (loading) {
    return <p role="status" className="rounded-2xl border bg-card px-6 py-6 text-lg text-muted-foreground">Se încarcă…</p>
  }
  if (calls.length === 0) {
    return <p className="rounded-2xl border bg-card px-6 py-6 text-lg">Nicio factură clasificată de Jev în această perioadă.</p>
  }
  return (
    <div className="overflow-hidden rounded-2xl border bg-card">
      <Table className="min-w-[860px]">
        <TableHeader>
          <TableRow>
            <TableHead>Când</TableHead>
            <TableHead>Client</TableHead>
            <TableHead>Furnizor și factură</TableHead>
            <TableHead>Cont</TableHead>
            <TableHead>Cât de sigur</TableHead>
            <TableHead className="text-right">Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {calls.map((call, index) => (
            <TableRow key={`${call.message_id}-${index}`}>
              <TableCell className="whitespace-nowrap">{formatWhen(call.called_at)}</TableCell>
              <TableCell>{call.client_name ?? (call.cui ? `CUI ${call.cui}` : '—')}</TableCell>
              <TableCell>
                {call.message_id === 'rule-test' ? (
                  <span className="font-semibold">Probă de reguli</span>
                ) : (
                  <Link to={`/clienti/${call.cui}/facturi/${call.message_id}`} className="font-semibold">
                    {call.message_type && isIssued({ message_type: call.message_type })
                      ? `Emisă către ${call.customer_name ?? 'Client necunoscut'}`
                      : call.supplier_name ?? 'Furnizor necunoscut'}{' '}
                    · {call.invoice_number}
                  </Link>
                )}
              </TableCell>
              <TableCell className="font-heading text-lg font-bold">{call.choice}</TableCell>
              <TableCell><Sureness call={call} /></TableCell>
              <TableCell className="text-right whitespace-nowrap" title={formatUsdExact(call.cost_usd)}>{formatUsd(call.cost_usd)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function Sureness({ call }: { call: JevCall }) {
  if (call.error) return <Badge className="bg-attention text-attention-foreground">nu a răspuns</Badge>
  if (call.confidence === null) return <Badge className="bg-muted text-foreground">nu a spus</Badge>
  return call.classification_status === 'review' ? (
    <Badge className="bg-attention text-attention-foreground">{formatPercent(call.confidence)} · de verificat</Badge>
  ) : (
    <Badge className="bg-done text-done-foreground">{formatPercent(call.confidence)}</Badge>
  )
}
