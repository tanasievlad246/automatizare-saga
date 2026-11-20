import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, CodeXml } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { ApiError, api } from '../api'
import { confirmedToast } from '../archive/archiveTexts'
import { COPY_REFUSED, copyText } from '../clipboard'
import { showError } from '../errorMessages'
import { formatWhen } from '../format'
import type { Invoice, WaitingFile } from '../types'
import { opensWindowsHere, pathOnThisPC, useWhere } from '../where'
import { DownloadFileButton } from './DownloadFileButton'
import { FileInvoicesTable } from './FileInvoicesTable'
import { FileXmlDialog } from './FileXmlDialog'
import type { SeenOf } from './useSeenFiles'
import { FILES_TAB, afterImportLine, fileSummary } from './waitingFiles'

/**
 * One file waiting for SAGA: its name, where it is, when it was written, how many invoices it
 * holds and what they are worth, its XML in a window, and its invoices in a table. It can be
 * saved on this computer, and „Fișier importat” marks its invoices as imported and moves it to
 * the archive. `seen`: what the person has seen of this file; that version is the one confirmed,
 * so a file written again since is refused. `stale`: the client's folder is not up to date, so
 * the file may not be what the screen shows: it is neither handed out nor confirmed.
 * `onDownloaded`: the version the file was saved in.
 */
export function WaitingFileCard({
  cui, file, invoices, stale, seen, onDownloaded,
}: {
  cui: string
  file: WaitingFile
  invoices: Invoice[]
  stale: boolean
  seen: SeenOf
  onDownloaded: (version: string | null) => void
}) {
  const queryClient = useQueryClient()
  const [showingXml, setShowingXml] = useState(false)
  // By one of its invoices: the folder the file is really in.
  const openFolder = useMutation({ mutationFn: () => api.openFolderOf(file.ids[0]), onError: showError })
  const refresh = () => {
    for (const key of ['invoices', 'invoice', 'clients', 'saga-archive']) queryClient.invalidateQueries({ queryKey: [key] })
  }
  const markImported = useMutation({
    mutationFn: () => api.confirmSagaImport(cui, seen.version ?? file.version, file.name),
    onMutate: seen.attempt,
    onSuccess: ({ archive, versions }) => {
      seen.confirmed(versions)
      refresh()
      if (archive) toast.success(confirmedToast(archive.invoices, archive.files.length))
    },
    onError: (error) => {
      // Changed since it was seen, or no longer waiting under this name: said here, on its card,
      // and the refresh brings the file as it is now.
      if (error instanceof ApiError && (error.code === 'saga_files_changed' || error.code === 'not_found')) {
        seen.refused()
        refresh()
      } else {
        // A file gone from the folder: the refresh brings the notice with „Încearcă din nou”.
        if (error instanceof ApiError && error.code === 'saga_files_stale') refresh()
        showError(error)
      }
    },
  })
  const where = useWhere()
  const path = pathOnThisPC(file.path, where) // as this computer reaches it
  const summary = fileSummary(invoices, file.invoices)
  const showXml = () => {
    seen.look()
    setShowingXml(true)
  }
  const showFolder = () => {
    seen.look()
    openFolder.mutate()
  }
  const copyPath = () => {
    seen.look()
    return copyText(path).then(
      () => toast.success('Calea a fost copiată.'),
      () => toast.error('Calea nu a fost copiată.', { description: COPY_REFUSED, duration: Infinity }),
    )
  }

  return (
    <li className="flex flex-col gap-3 rounded-2xl border bg-card px-5 py-4.5">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h3 className="min-w-0 font-mono text-[1.02rem] font-bold break-all">{file.name}</h3>
        {file.written_at && <span className="text-muted-foreground sm:ml-auto">Scris: {formatWhen(file.written_at)}</span>}
      </div>
      <p className="rounded-lg bg-background px-3.5 py-3 font-mono text-[0.88rem] break-all">{path}</p>
      {!file.present && <p className="font-semibold text-attention-foreground">{FILES_TAB.missing}</p>}
      <div>
        <p>
          <strong>{summary.count}</strong>
          {summary.total && <> · Total <strong>{summary.total}</strong></>}
        </p>
        {summary.kinds && <p className="text-[0.9rem] text-muted-foreground">{summary.kinds}</p>}
      </div>
      {seen.changed && (
        <Notice tone="attention">
          <p className="font-bold">{FILES_TAB.changedTitle}</p>
          <p>{FILES_TAB.changedText}</p>
        </Notice>
      )}
      {/* Named with their file: the same buttons repeat on every card. */}
      <div className="flex flex-wrap items-center gap-2.5">
        {file.present && (
          <DownloadFileButton cui={cui} name={file.name} size="sm" disabled={stale} onDownloaded={onDownloaded} />
        )}
        {file.present && (
          <Button variant="outline" size="sm" aria-label={`${FILES_TAB.xmlButton}: ${file.name}`} onClick={showXml}>
            <CodeXml aria-hidden />
            {FILES_TAB.xmlButton}
          </Button>
        )}
        <Button variant="outline" size="sm" aria-label={`Copiază calea: ${file.name}`} onClick={copyPath}>Copiază calea</Button>
        {opensWindowsHere(where) && (
          <Button
            variant="outline" size="sm" aria-label={`Deschide folderul: ${file.name}`}
            disabled={openFolder.isPending || file.ids.length === 0} onClick={showFolder}
          >
            Deschide folderul
          </Button>
        )}
        {/* Apart from the others, at the end of the row: it is the one that changes something. */}
        <Button
          variant="outline" size="sm" aria-label={`${FILES_TAB.importedButton}: ${file.name}`}
          className="border-2 border-done-foreground font-bold text-done-foreground sm:ml-auto"
          // Off once it went through: the card leaves with the next reload.
          disabled={stale || !file.present || markImported.isPending || markImported.isSuccess}
          onClick={() => markImported.mutate()}
        >
          <Check aria-hidden />
          {FILES_TAB.importedButton}
        </Button>
      </div>
      <p className="text-[0.9rem] text-muted-foreground">{afterImportLine(file.invoices)}</p>
      {invoices.length > 0 && <FileInvoicesTable fileName={file.name} memory={`${cui}/${file.name}`} invoices={invoices} />}
      {showingXml && (
        <FileXmlDialog cui={cui} file={file} summary={summary.count.toLowerCase()} onClose={() => setShowingXml(false)} />
      )}
    </li>
  )
}
