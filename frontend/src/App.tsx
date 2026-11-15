import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HashRouter, Route, Routes } from 'react-router'
import { BackupsPage } from './backups/BackupsPage'
import { ClientsPage } from './clients/ClientsPage'
import { CostsPage } from './costs/CostsPage'
import { ClientInvoicesPage } from './invoices/ClientInvoicesPage'
import { InvoicePage } from './invoices/InvoicePage'
import { JournalPage } from './journal/JournalPage'
import { AppShell } from './layout/AppShell'
import { SchedulePage } from './schedule/SchedulePage'
import { RulesPage } from './rules/RulesPage'
import { RuleTestPage } from './rules/test/RuleTestPage'
import { SecretsPage } from './secrets/SecretsPage'

// Everything lives on this one computer, so a failed request is not worth retrying
// silently: the person should see the message straight away.
// networkMode 'always': the program is on this PC, so it answers with the network cable out
// too. Left to wait for the network, a restore would show as running with nothing sent, and
// would start by itself when the network came back.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false, networkMode: 'always' },
    mutations: { networkMode: 'always' },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      {/* Addresses after "#" never reach the server, so the page works from one file. */}
      <HashRouter>
        <Routes>
          <Route element={<AppShell />}>
            <Route index element={<ClientsPage />} />
            <Route path="clienti/:cui" element={<ClientInvoicesPage />} />
            <Route path="clienti/:cui/facturi/:id" element={<InvoicePage />} />
            <Route path="descarcare-automata" element={<SchedulePage />} />
            <Route path="reguli" element={<RulesPage />} />
            {/* The menu keeps "Reguli de clasificare" marked here: its address starts with /reguli. */}
            <Route path="reguli/test" element={<RuleTestPage />} />
            <Route path="costuri" element={<CostsPage />} />
            <Route path="copii" element={<BackupsPage />} />
            <Route path="jurnal" element={<JournalPage />} />
            <Route path="chei" element={<SecretsPage />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  )
}
