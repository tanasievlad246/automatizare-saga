import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { Notice } from '@/components/Notice'
import { PageTitle } from '@/components/PageTitle'
import { Button } from '@/components/ui/button'
import { api } from '../api'
import { errorMessage } from '../errorMessages'
import { countOf, formatDate } from '../format'
import { AnafLoginDialog } from '../layout/AnafLoginDialog'
import { SecretField } from './SecretField'

// What each key is, in the order they are shown.
const NAMES: Record<string, string> = {
  openrouter_api_key: 'Cheia OpenRouter (pentru Jev)',
  anaf_client_id: 'ANAF — Client ID',
  anaf_client_secret: 'ANAF — Client Secret',
  api_key: 'Cheia programului (pentru Power Automate)',
  anaf_access_token: 'ANAF — cheia de acces primită la conectare',
  anaf_refresh_token: 'ANAF — cheia de reînnoire primită la conectare',
}

// The guide in Romanian, kept with the program's source.
const ANAF_KEYS_GUIDE = 'https://github.com/tanasievlad246/automatizare-saga/blob/main/README-ANAF.md'

/** Every key the program holds, each hidden until the person asks to see it. */
export function SecretsPage() {
  const [loginOpen, setLoginOpen] = useState(false)
  const { data, error } = useQuery({ queryKey: ['secrets'], queryFn: api.secrets })
  const login = useQuery({ queryKey: ['auth'], queryFn: api.authStatus }).data

  return (
    <div className="flex max-w-[54rem] flex-col gap-5">
      <PageTitle title="Chei și parole">
        Cu aceste chei programul vorbește cu ANAF și cu Jev. De obicei se completează o singură dată.
      </PageTitle>
      <Notice tone="attention">
        <span className="font-semibold">Nu arătați și nu trimiteți nimănui aceste chei.</span>
      </Notice>
      {error && <Notice tone="attention">{errorMessage(error)}</Notice>}
      <a
        href={ANAF_KEYS_GUIDE}
        target="_blank"
        rel="noreferrer"
        className="inline-flex min-h-11 items-center self-start font-semibold"
      >
        Cum obțin Client ID și Client Secret de la ANAF? Pașii, unul câte unul
      </a>

      <div className="flex flex-col gap-3">
        {data?.secrets.map((secret) => (
          <SecretField key={secret.key} secret={secret} name={NAMES[secret.key] ?? secret.key} />
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl border bg-card px-5 py-4.5">
        <div className="min-w-0 flex-[1_1_320px]">
          <div className="text-lg font-bold">Conectarea la ANAF</div>
          <div className="text-muted-foreground">
            {login && login.state !== 'needs_login'
              ? `Valabilă până la ${formatDate(login.refresh_expires_at)}, adică încă ${countOf(login.refresh_days_left ?? 0, 'o zi', 'zile')}. Apoi este nevoie din nou de tokenul USB.`
              : 'Nu sunteți conectat. Este nevoie de tokenul USB și de PIN.'}
          </div>
        </div>
        <Button variant="outline" onClick={() => setLoginOpen(true)}>
          {login && login.state !== 'needs_login' ? 'Conectează din nou' : 'Conectare la ANAF'}
        </Button>
      </div>
      <AnafLoginDialog open={loginOpen} onClose={() => setLoginOpen(false)} />
    </div>
  )
}
