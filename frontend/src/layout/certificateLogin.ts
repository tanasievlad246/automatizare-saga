import { ApiError } from '../api'
import { errorMessage } from '../errorMessages'

/**
 * What the ANAF login window shows. `waiting` carries the number of the try it waits for:
 * the answer of an earlier try, one the person gave up on, changes nothing on screen.
 */
export type LoginView =
  | { kind: 'certificate'; note?: string }
  | { kind: 'waiting'; attempt: number }
  | { kind: 'failed'; error: unknown }
  | { kind: 'browser' }

export type LoginEvent =
  | { type: 'ask'; attempt: number } // "Conectează-mă cu certificatul" or "Încearcă din nou"
  | { type: 'failed'; attempt: number; error: unknown } // the answer to that try
  | { type: 'giveUp' } // "Renunță"
  | { type: 'browser' } // "Conectare prin browser"

/** The first view: the certificate way where the program offers it, else the browser steps
 *  as they always were (also while the login state has not been read yet). */
export function openingView(certificateLogin: boolean | undefined): LoginView {
  return certificateLogin ? { kind: 'certificate' } : { kind: 'browser' }
}

export function nextView(view: LoginView, event: LoginEvent): LoginView {
  switch (event.type) {
    case 'ask':
      return view.kind === 'waiting' ? view : { kind: 'waiting', attempt: event.attempt }
    case 'giveUp':
      return view.kind === 'waiting' ? { kind: 'certificate' } : view
    case 'browser':
      return { kind: 'browser' }
    case 'failed':
      if (!isWaitingFor(view, event.attempt)) return view
      if (event.error instanceof ApiError && event.error.code === 'login_cancelled') {
        return { kind: 'certificate', note: errorMessage(event.error) }
      }
      return { kind: 'failed', error: event.error }
  }
}

export function isWaitingFor(view: LoginView, attempt: number): boolean {
  return view.kind === 'waiting' && view.attempt === attempt
}
