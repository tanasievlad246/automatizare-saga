import { AUTHOR, AUTHOR_EMAIL, SINCE } from './author'

/** Under the version at the foot of the menu: who made the program, and how to write to them. */
export function Credits() {
  return (
    <div className="mt-3 flex flex-col gap-0.5 border-t px-3.5 pt-3 text-sm text-muted-foreground">
      <span>© {SINCE} {AUTHOR}</span>
      <a href={`mailto:${AUTHOR_EMAIL}`} className="break-all text-muted-foreground">{AUTHOR_EMAIL}</a>
    </div>
  )
}
