import { Link } from 'react-router'
import { ErrorNotice } from '@/components/ErrorNotice'
import { PageTitle } from '@/components/PageTitle'
import { switchedOffLine } from '../clients/switchedOff'
import { ScheduleForm } from './ScheduleForm'
import { ScheduleStateCard } from './ScheduleStateCard'
import { useSchedule } from './useSchedule'

/** The program downloads by itself: when it does, what happened the last time, and the rules of it. */
export function SchedulePage() {
  const { data: status, error, isPending } = useSchedule()
  return (
    <div className="flex max-w-[66rem] flex-col gap-5">
      <PageTitle title="Descărcare automată">
        Programul descarcă singur facturile de la ANAF, pentru toți clienții porniți, în zilele și la orele alese.
        Fiecare factură nouă își primește contul din reguli sau de la Jev, la fel ca atunci când descărcați dumneavoastră.
      </PageTitle>
      {error && <ErrorNotice error={error} />}
      {isPending && <p role="status" className="text-lg text-muted-foreground">Se încarcă…</p>}
      {status && (
        <>
          <ScheduleStateCard status={status} />
          <ScheduleForm saved={status} />
          <section aria-label="Bine de știut" className="flex flex-col gap-3 rounded-2xl border bg-card px-5.5 py-5">
            <h2 className="font-sans text-xl font-bold">Bine de știut</h2>
            <ul className="flex list-disc flex-col gap-2.5 pl-6 text-lg">
              <li>
                Programul trebuie să fie pornit; el pornește singur odată cu Windows. Dacă la ora aleasă calculatorul era
                oprit, descărcarea se face imediat ce îl porniți.
              </li>
              <li>
                {switchedOffLine(status.clients_on, status.clients_off) ?? 'Se descarcă toți clienții din listă.'}{' '}
                <Link to="/" className="font-semibold">Vezi clienții</Link>
              </li>
              <li>
                Dacă ANAF nu poate fi contactat, de exemplu fără internet, programul mai încearcă de trei ori, din sfert în
                sfert de oră.
              </li>
              <li>
                Jev costă la fel ca la descărcarea făcută de dumneavoastră. Costurile sunt pe pagina „Costuri Jev”.
              </li>
            </ul>
          </section>
        </>
      )}
    </div>
  )
}
