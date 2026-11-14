import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HashRouter, Route, Routes } from 'react-router'
import { ClientsPage } from './clients/ClientsPage'
import { CostsPage } from './costs/CostsPage'
import { ClientInvoicesPage } from './invoices/ClientInvoicesPage'
import { InvoicePage } from './invoices/InvoicePage'
import { AppShell } from './layout/AppShell'
import { RulesPage } from './rules/RulesPage'
import { SecretsPage } from './secrets/SecretsPage'

// Everything lives on this one computer, so a failed request is not worth retrying
// silently: the person should see the message straight away.
const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
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
            <Route path="reguli" element={<RulesPage />} />
            <Route path="costuri" element={<CostsPage />} />
            <Route path="chei" element={<SecretsPage />} />
          </Route>
        </Routes>
      </HashRouter>
    </QueryClientProvider>
  )
}
