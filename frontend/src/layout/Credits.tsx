import { AUTHOR, AUTHOR_EMAIL, SINCE } from './author'

/** Under the version at the foot of the menu: who made the program, and how to write to them. */
export function Credits() {
  // The address is wider than the menu. It breaks before the "@" and nowhere else: the
  // part before it fits on a line of its own, and an address cut mid-word reads as two.
  const [name, domain] = AUTHOR_EMAIL.split('@')
  return (
    <div className="mt-3 flex flex-col gap-0.5 border-t px-3.5 pt-3 text-sm text-muted-foreground">
      <span>© {SINCE} {AUTHOR}</span>
      <a href={`mailto:${AUTHOR_EMAIL}`} className="text-muted-foreground underline-offset-2 hover:underline">
        {name}
        <wbr />@{domain}
      </a>
    </div>
  )
}
