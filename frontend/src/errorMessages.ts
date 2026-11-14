// The program explains failures in English, for the log. The screen says them in Romanian,
// in words that tell the person what to do next.

import { toast } from 'sonner'
import { ApiError } from './api'

const MESSAGES: Record<string, string> = {
  login_needed: 'Trebuie să vă conectați din nou la ANAF. Apăsați butonul de conectare din bara de sus.',
  login_code_expired: 'Adresa lipită a expirat sau a mai fost folosită. Începeți conectarea din nou.',
  invalid_cui: 'CUI-ul nu este corect. Verificați cifrele.',
  invalid_input: 'Ceva din ce ați completat nu este corect. Verificați și încercați din nou.',
  no_spv_rights: 'Certificatul nu are drepturi în SPV pentru această firmă.',
  anaf_limit_reached: 'ANAF a limitat numărul de cereri pentru azi. Încercați mai târziu.',
  anaf_error: 'ANAF a răspuns cu o eroare. Încercați din nou puțin mai târziu.',
  network_error: 'Nu am putut ajunge la ANAF. Verificați conexiunea la internet.',
  not_found: 'Nu am găsit ce ați cerut. Poate a fost șters între timp.',
  busy: 'Se descarcă deja facturi. Așteptați să se termine, apoi încercați din nou.',
  config_error: 'Lipsește o setare. Verificați pagina „Chei și parole”.',
  not_classifiable: 'Contul acestei facturi nu poate fi schimbat acum.',
  jev_error: 'Jev nu a putut fi întrebat. Verificați cheia OpenRouter și creditul din cont.',
  unauthorized: 'Pagina nu mai are voie să vorbească cu programul. Închideți pagina și porniți programul din nou.',
  unreachable: 'Programul nu răspunde. Verificați dacă este pornit.',
}
const UNKNOWN = 'A apărut o problemă în program.'

export function errorMessage(error: unknown): string {
  return (error instanceof ApiError && MESSAGES[error.code]) || UNKNOWN
}

/** Show a failure as a notice: the Romanian sentence, with the original kept as detail. */
export function showError(error: unknown): void {
  const detail = error instanceof Error ? error.message : String(error)
  toast.error(errorMessage(error), { description: `Detalii tehnice: ${detail}` })
}
