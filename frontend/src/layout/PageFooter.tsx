import { AUTHOR, AUTHOR_EMAIL, AUTHOR_PHONE, AUTHOR_PHONE_SHOWN, SINCE } from './author'

/** Across the whole page, after the menu and the content: who made the program, and how to write to or call them. */
export function PageFooter() {
  return (
    <footer className="flex flex-wrap items-center gap-x-2.5 gap-y-1 border-t bg-card px-7 py-3 text-sm text-muted-foreground">
      <span>© {SINCE} {AUTHOR}</span>
      <span aria-hidden>·</span>
      <a href={`mailto:${AUTHOR_EMAIL}`} className="text-muted-foreground underline-offset-2 hover:underline">{AUTHOR_EMAIL}</a>
      <span aria-hidden>·</span>
      <a href={`tel:${AUTHOR_PHONE}`} className="text-muted-foreground underline-offset-2 hover:underline">{AUTHOR_PHONE_SHOWN}</a>
    </footer>
  )
}
