import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ApiError, api } from '../api'
import { showError } from '../errorMessages'
import { saveFile } from '../saveFile'
import { FILES_TAB } from './waitingFiles'

/**
 * Saves one of a client's waiting files on the computer the page is open on, for whoever cannot
 * reach the folder the program writes in. Goes in a row of buttons that wraps: from the second
 * download on, a line about the browser's "(1)" takes a row of its own under them.
 * `onDownloaded`: the version of the file as it was given.
 */
export function DownloadFileButton({
  cui, name, size, disabled = false, onDownloaded,
}: {
  cui: string
  name: string
  size?: 'sm'
  disabled?: boolean
  onDownloaded?: (version: string | null) => void
}) {
  const queryClient = useQueryClient()
  const [times, setTimes] = useState(0)
  const download = useMutation({
    mutationFn: () => api.sagaFile(cui, name),
    onSuccess: ({ blob, version }) => {
      saveFile(blob, name)
      setTimes((count) => count + 1)
      onDownloaded?.(version)
      toast.success(FILES_TAB.downloaded)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'not_found') {
        // Gone, or written again under another name: the lists are read again and show what is there now.
        toast.error(FILES_TAB.xmlGone)
        for (const key of ['invoices', 'invoice']) queryClient.invalidateQueries({ queryKey: [key] })
      } else {
        showError(error)
      }
    },
  })

  return (
    <>
      {/* Named with its file: the same button repeats on every card. */}
      <Button
        variant="outline" size={size} aria-label={`${FILES_TAB.downloadButton}: ${name}`}
        disabled={disabled || download.isPending} onClick={() => download.mutate()}
      >
        <Download aria-hidden />
        {FILES_TAB.downloadButton}
      </Button>
      {times > 1 && (
        <p role="status" className="order-last basis-full text-[0.9rem] text-muted-foreground">{FILES_TAB.downloadedAgain}</p>
      )}
    </>
  )
}
