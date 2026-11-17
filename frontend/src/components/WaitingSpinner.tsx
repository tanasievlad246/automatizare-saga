import { cn } from '@/lib/utils'

/**
 * Shown while the program works on something whose end it cannot measure: a ring that turns,
 * so it never looks stuck partway, as a bar standing at 40% did. The words beside it say
 * what is happening; the ring only shows that the program has not stopped.
 */
export function WaitingSpinner({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 48 48"
      className={cn('size-12 shrink-0 animate-spin [animation-duration:1.2s] motion-reduce:animate-none', className)}
    >
      <circle cx="24" cy="24" r="20" fill="none" strokeWidth="5" className="stroke-muted" />
      {/* About a third of the ring, 40 of its 126 units, in the main colour. */}
      <circle
        cx="24" cy="24" r="20" fill="none" strokeWidth="5" strokeLinecap="round" strokeDasharray="40 126"
        className="stroke-primary"
      />
    </svg>
  )
}
