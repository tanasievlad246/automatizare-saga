import { useQuery } from '@tanstack/react-query'
import { Folder } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import { shortPath } from '../format'
import { SagaFilesDialog } from './SagaFilesDialog'

/** In the top bar of every screen: where the files for SAGA go, and the way to change that and how they are written. */
export function SagaFolderChip() {
  const [changing, setChanging] = useState(false)
  const settings = useQuery({ queryKey: ['saga-folder'], queryFn: api.sagaFolder }).data
  const folder = settings?.saga_folder

  return (
    <>
      <button
        type="button"
        title={folder}
        // Nothing to change until the program has said what is set now.
        disabled={!settings}
        onClick={() => setChanging(true)}
        // min-w-0: in a narrow top bar the chip gives way, and only its path is cut short.
        className="flex min-h-11 max-w-full min-w-0 cursor-pointer items-center gap-2 rounded-full border bg-background px-4 font-semibold outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring"
      >
        <Folder aria-hidden className="size-5 shrink-0" />
        <span className="shrink-0 font-medium whitespace-nowrap text-muted-foreground">Folder SAGA</span>
        <span className="min-w-0 truncate">{folder ? shortPath(folder) : '…'}</span>
        <span className="shrink-0 whitespace-nowrap text-primary underline">Schimbă</span>
      </button>
      {changing && settings && <SagaFilesDialog saved={settings} onClose={() => setChanging(false)} />}
    </>
  )
}
