import { useQuery } from '@tanstack/react-query'
import { ChartColumn, KeyRound, ListChecks, Users } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Toaster } from '@/components/ui/sonner'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { countOf } from '../format'
import { AnafConnectionBadge } from './AnafConnectionBadge'
import { ProgramVersion } from './ProgramVersion'
import { SagaFolderField } from './SagaFolderField'
import { UpdateNotice } from './UpdateNotice'

const SCREENS = [
  { to: '/', label: 'Clienți', icon: Users },
  { to: '/reguli', label: 'Reguli de clasificare', icon: ListChecks },
  { to: '/costuri', label: 'Costuri Jev', icon: ChartColumn },
  { to: '/chei', label: 'Chei și parole', icon: KeyRound },
]

/** What every screen shares: the SAGA folder and the ANAF connection on top, the menu at the side. */
export function AppShell() {
  const { pathname } = useLocation()
  // Shown in the menu: an invoice Jev was sure about is never opened, so its proposed rule
  // would otherwise never be seen.
  const proposedRules = useQuery({ queryKey: ['proposed-rules'], queryFn: api.proposedRules }).data?.count ?? 0
  const update = useQuery({ queryKey: ['program-update'], queryFn: () => api.updateStatus() }).data
  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-7 gap-y-3 border-b bg-card px-7 py-3.5">
        <div className="font-heading text-xl font-bold">e-Factura pentru SAGA</div>
        <SagaFolderField />
        <AnafConnectionBadge />
      </header>
      <div className="flex flex-wrap">
        <nav aria-label="Meniu" className="flex flex-[1_1_272px] flex-col gap-1.5 px-4 py-6">
          {SCREENS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              // A client's invoices belong to "Clienți", so that entry stays lit there too.
              className={({ isActive }) =>
                cn(
                  'flex min-h-12 items-center gap-3 rounded-lg px-3.5 py-1.5 no-underline',
                  isActive || (to === '/' && location.hash.startsWith('#/clienti'))
                    ? 'bg-secondary font-semibold text-secondary-foreground'
                    : 'font-medium text-foreground hover:bg-muted',
                )
              }
            >
              <Icon aria-hidden className="size-5.5 shrink-0" />
              <span className="flex flex-col">
                {label}
                {to === '/reguli' && proposedRules > 0 && (
                  <span className="text-sm font-bold text-primary in-aria-[current=page]:text-secondary-foreground">
                    {countOf(proposedRules, 'o regulă propusă', 'reguli propuse')}
                  </span>
                )}
              </span>
            </NavLink>
          ))}
          {update && <ProgramVersion status={update} />}
        </nav>
        <main className="min-w-0 max-w-[66rem] flex-[999_1_560px] px-8 pt-7 pb-12">
          {update?.update_available && <UpdateNotice status={update} />}
          <ErrorBoundary key={pathname}>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
      <Toaster position="bottom-right" richColors closeButton toastOptions={{ closeButtonAriaLabel: 'Închide' }} />
    </div>
  )
}
