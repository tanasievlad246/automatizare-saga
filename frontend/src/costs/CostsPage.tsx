import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { PillTabs } from '@/components/PillTabs'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { MOST_CALLS_LISTED, api } from '../api'
import { errorMessage } from '../errorMessages'
import { formatUsd, today } from '../format'
import type { CostGroup } from '../types'
import { CostsByPeriodTable } from './CostsByPeriodTable'
import { JevCallsTable } from './JevCallsTable'

const GROUPS: { value: CostGroup; label: string; heading: string }[] = [
  { value: 'day', label: 'pe zile', heading: 'Pe zile' },
  { value: 'week', label: 'pe săptămâni', heading: 'Pe săptămâni' },
  { value: 'month', label: 'pe luni', heading: 'Pe luni' },
  { value: 'year', label: 'pe ani', heading: 'Pe ani' },
]

/** What Jev has cost between two days, broken down as the person asks, and what it was paid for. */
export function CostsPage() {
  const [since, setSince] = useState(startOfTheYear)
  const [until, setUntil] = useState(today)
  const [group, setGroup] = useState<CostGroup>('month')
  const range = { since, until }
  const costs = useQuery({ queryKey: ['costs', range, group], queryFn: () => api.costs(range, group) })
  const calls = useQuery({ queryKey: ['jev-calls', range], queryFn: () => api.jevCalls(range) })

  return (
    <div className="flex flex-col gap-6">
      <PageTitle title="Costuri Jev">
        Cât a costat clasificarea facturilor de către Jev. Regulile dumneavoastră nu costă nimic.
      </PageTitle>

      <div className="flex flex-wrap items-end gap-x-5 gap-y-3.5 rounded-2xl border bg-card px-5 py-4.5">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="costs-since">De la</Label>
          <Input id="costs-since" type="date" value={since} max={until} onChange={(event) => setSince(event.target.value)} className="w-auto" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="costs-until">Până la</Label>
          <Input id="costs-until" type="date" value={until} min={since} max={today()} onChange={(event) => setUntil(event.target.value)} className="w-auto" />
        </div>
        <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-1.5">
          <span className="font-semibold">Arată costul</span>
          <PillTabs label="Cum se împarte costul" options={GROUPS} value={group} onChange={setGroup} />
        </div>
      </div>

      {costs.error && <Notice tone="attention">{errorMessage(costs.error)}</Notice>}
      {costs.data && (
        <>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(240px,100%),1fr))] gap-4">
            <Figure name="Cost în perioada aleasă" value={formatUsd(costs.data.cost_usd)} />
            <Figure name="Facturi clasificate de Jev" value={costs.data.invoices.toLocaleString('ro-RO')} />
            <Figure name="Cost mediu pe factură" value={formatUsd(costs.data.average_cost_per_invoice_usd) || 'încă nimic'} />
          </div>
          <section className="flex flex-col gap-3">
            <h2 className="text-2xl">{GROUPS.find((each) => each.value === group)?.heading}</h2>
            <CostsByPeriodTable periods={costs.data.by_period} />
          </section>
        </>
      )}
      <section className="flex flex-col gap-3">
        <h2 className="text-2xl">Ce a clasificat Jev</h2>
        <JevCallsTable calls={calls.data?.calls ?? []} />
        {calls.data?.calls.length === MOST_CALLS_LISTED && (
          <p className="text-muted-foreground">
            Se văd cele mai recente {MOST_CALLS_LISTED.toLocaleString('ro-RO')}. Alegeți o perioadă mai scurtă ca să le vedeți pe celelalte.
          </p>
        )}
      </section>
    </div>
  )
}

function Figure({ name, value }: { name: string; value: string }) {
  return (
    <div className="rounded-2xl border bg-card px-5 py-4.5">
      <div className="font-semibold text-muted-foreground">{name}</div>
      <div className="font-heading text-[2.4rem] leading-tight font-bold">{value}</div>
    </div>
  )
}

function startOfTheYear(): string {
  return `${new Date().getFullYear()}-01-01`
}
