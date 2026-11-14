import { useQuery } from '@tanstack/react-query'
import { ChartColumn, DatabaseBackup, KeyRound, ListChecks, ScrollText, Users } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Toaster } from '@/components/ui/sonner'
import { cn } from '@/lib/utils'
import { api } from '../api'
import { countOf } from '../format'
import type { UpdateStatus } from '../types'
import { AnafConnectionBadge } from './AnafConnectionBadge'
import { Brand } from './Brand'
import { ProgramVersion } from './ProgramVersion'
import { SagaFolderChip } from './SagaFolderChip'
import { UpdateDialog } from './UpdateDialog'
import { UpdateNotice } from './UpdateNotice'

const SCREENS = [
  { to: '/', label: 'Clienți', icon: Users },
  { to: '/reguli', label: 'Reguli de clasificare', icon: ListChecks },
  { to: '/costuri', label: 'Costuri Jev', icon: ChartColumn },
  { to: '/copii', label: 'Copii de siguranță', icon: DatabaseBackup },
  { to: '/jurnal', label: 'Jurnal', icon: ScrollText },
  { to: '/chei', label: 'Chei și parole', icon: KeyRound },
]

/**
 * What every screen shares: the top bar (the product, the SAGA folder, the ANAF connection)
 * and the menu. The menu has a width of its own and never grows: on a wide monitor the
 * room goes to the screen's content. On a narrow window the menu sits above the content.
 */
export function AppShell() {
  const { pathname } = useLocation()
  // Shown in the menu: an invoice Jev was sure about is never opened, so its proposed rule
  // would otherwise never be seen.
  // Both are read again when the window is returned to: a page left open since yesterday
  // must not keep yesterday's answer.
  const proposedRules =
    useQuery({ queryKey: ['proposed-rules'], queryFn: api.proposedRules, refetchOnWindowFocus: true }).data?.count ?? 0
  const update = useQuery({ queryKey: ['program-update'], queryFn: () => api.updateStatus(), refetchOnWindowFocus: true }).data
  // The update window is held here, not by the notice that opens it: once the update has
  // worked the notice goes away, and it must not take the window and its "Continuă" with it.
  // What is kept is the status as it was when the window was opened.
  const [updating, setUpdating] = useState<UpdateStatus | null>(null)
  return (
    <div className="flex min-h-screen flex-col">
      {/* One row once the menu is at the side: a bar that sticks must not take two rows of
          a small screen. The SAGA folder is what gives way, by showing less of its path. */}
      <header className="sticky top-0 z-30 flex flex-wrap items-center gap-x-5 gap-y-3 border-b bg-card px-7 py-3 min-[60rem]:flex-nowrap">
        <Brand />
        <div className="ml-auto flex min-w-0 flex-wrap items-center gap-2.5 min-[60rem]:flex-nowrap">
          <SagaFolderChip />
          <AnafConnectionBadge />
        </div>
      </header>
      <div className="flex flex-1 flex-col min-[60rem]:flex-row">
        <nav
          aria-label="Meniu"
          className="flex shrink-0 flex-row flex-wrap gap-1.5 px-4 pt-4 min-[60rem]:w-[15.5rem] min-[60rem]:flex-col min-[60rem]:flex-nowrap min-[60rem]:py-6"
        >
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
        <main className="min-w-0 flex-1 px-8 pt-7 pb-12">
          {/* Wide enough for tables on a large monitor; screens of text set a narrower width themselves. */}
          <div className="max-w-[96rem]">
            {update?.update_available && <UpdateNotice status={update} onUpdate={() => setUpdating(update)} />}
            <ErrorBoundary key={pathname}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
      {updating && <UpdateDialog status={updating} onClose={() => setUpdating(null)} />}
      {/* pointer-events-auto: a window that is open switches the rest of the page off for
          the mouse; the messages must stay readable and closable above it. */}
      <Toaster
        position="bottom-right"
        richColors
        closeButton
        className="pointer-events-auto"
        toastOptions={{ closeButtonAriaLabel: 'Închide' }}
      />
    </div>
  )
}
