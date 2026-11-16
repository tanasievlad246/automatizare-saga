import { Link } from 'react-router'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { countOf } from '../format'
import type { Invoice } from '../types'
import { firstPhrase } from './AccountChooser'
import { accountsUsed, linesLeft, linesLeftNote } from './lineAccounts'

/**
 * The accounts of an invoice decided line by line, added up: each account with how many
 * lines are on it, what still waits, and one account for every line at once. Each line's own
 * account is in the table of lines.
 */
export function LineAccountsCard({
  invoice, accounts, onChooseAll,
}: { invoice: Invoice; accounts: Record<string, string>; onChooseAll: () => void }) {
  const entries = invoice.line_accounts ?? []
  const used = accountsUsed(entries)
  const left = linesLeft(entries)
  const imported = invoice.uploaded_to_accounting
  // Held back without asking anyone: the same supplier, number and date are saved already.
  const sentTwice =
    invoice.classification_status === 'review' &&
    invoice.possible_duplicate_of !== null &&
    used.length === 0 &&
    entries.every((entry) => !entry.suggested_cont)

  return (
    <section aria-label="Conturile facturii" className="flex flex-col gap-3 rounded-2xl border bg-card px-5 pt-4.5 pb-5.5">
      <h2 className="font-sans text-xl font-bold">Conturile facturii</h2>
      {sentTwice && !imported && (
        <Notice tone="attention">
          <p className="font-bold">Factura pare trimisă de două ori</p>
          <p>
            Are același furnizor, același număr și aceeași dată ca o factură salvată mai devreme. Dacă este aceeași
            factură, nu o importați: bifați mai jos „Am importat factura în SAGA”. Dacă este alta, alegeți conturile.
          </p>
          <Link to={`/clienti/${invoice.cui}/facturi/${invoice.possible_duplicate_of}`} className="font-semibold">
            Vezi factura salvată mai devreme
          </Link>
        </Notice>
      )}
      {used.length > 0 ? (
        <ul className="flex flex-col gap-1.5">
          {used.map(({ cont, lines }) => (
            <li key={cont} className="flex items-baseline justify-between gap-3">
              <span className="min-w-0">
                <span className="font-heading text-xl font-bold">{cont}</span>
                {accounts[cont] ? <span> · {firstPhrase(accounts[cont])}</span> : null}
              </span>
              <span className="shrink-0 text-muted-foreground">{countOf(lines, 'o linie', 'linii')}</span>
            </li>
          ))}
        </ul>
      ) : (
        !sentTwice && <p>Nicio linie nu are încă un cont.</p>
      )}
      {left > 0 && !imported && <Notice tone="attention">{linesLeftNote(left)}</Notice>}
      {imported ? (
        <p className="text-muted-foreground">Factura este importată în SAGA, așa că aici conturile nu se mai schimbă.</p>
      ) : (
        <Button variant="outline" className="h-auto min-h-11 self-start py-2 text-left whitespace-normal" onClick={onChooseAll}>
          Pune același cont pe toate liniile
        </Button>
      )}
    </section>
  )
}
