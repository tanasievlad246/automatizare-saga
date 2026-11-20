// Where the page is opened: on the computer that runs the program, or on another one of the
// office network when the program runs in server mode (on the NAS, say).

import { useQuery } from '@tanstack/react-query'
import { api } from './api'
import type { Where } from './types'

/** Asked once: it does not change while the program runs. */
export function useWhere(): Where | undefined {
  return useQuery({ queryKey: ['where'], queryFn: api.where, staleTime: Infinity }).data
}

/**
 * Can the program open a window for this browser: a folder, the folder picker? Only on its own
 * computer; elsewhere the window would open there, not here. Until it has said, as it always was.
 */
export function opensWindowsHere(where: Where | undefined): boolean {
  return where?.on_this_computer ?? true
}

/** Under a folder field, where "Alege folderul" would open its window on the other computer. */
export function typeTheFolder(example: string): string {
  return `Programul rulează pe alt calculator, așa că fereastra de alegere nu se deschide aici. Scrieți calea folderului așa cum o vede acel calculator, de exemplu ${example} pe NAS.`
}

export type PcKind = 'windows' | 'mac' | 'other'

export function pcKind(userAgent: string = navigator.userAgent): PcKind {
  if (/Windows/i.test(userAgent)) return 'windows'
  if (/Macintosh|Mac OS X/i.test(userAgent)) return 'mac'
  return 'other'
}

/**
 * A path in the folder for SAGA as this computer reaches it, through the shared folder set in
 * config.toml ([server] saga_folder_windows or saga_folder_mac). Anything else stays as the
 * program wrote it.
 */
export function pathOnThisPC(path: string, where: Where | undefined, kind: PcKind = pcKind()): string {
  if (!where || where.mode !== 'network' || where.on_this_computer) return path
  const share = kind === 'windows' ? where.saga_folder_windows : kind === 'mac' ? where.saga_folder_mac : null
  if (!share) return path
  const folder = where.saga_folder.replace(/[\\/]+$/, '')
  const inside = path === folder || path.startsWith(`${folder}/`) || path.startsWith(`${folder}\\`)
  if (!inside) return path
  const rest = path.slice(folder.length).split(/[\\/]+/).filter(Boolean)
  // The folder itself is the share as written: a mapped drive keeps its backslash ("S:\", its root).
  if (rest.length === 0) return share
  return [share.replace(/[\\/]+$/, ''), ...rest].join(kind === 'windows' ? '\\' : '/')
}
