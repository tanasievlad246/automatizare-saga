import { ChevronLeft, ChevronRight } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { type Page, pageNumbers } from './paging'

/**
 * The bar under a long list: which rows are seen, and buttons to the other pages. Nothing for a
 * list that fits on one page. "Înapoi" and "Înainte" stay focusable at the ends (a disabled button
 * would drop the keyboard focus after the last "Înainte"); they only do nothing there.
 */
export function Pager({ page, label, line, onPage }: { page: Page<unknown>; label: string; line: string; onPage: (page: number) => void }) {
  if (page.pages <= 1) return null
  const go = (to: number) => {
    if (to >= 1 && to <= page.pages && to !== page.page) onPage(to)
  }
  const atStart = page.page === 1
  const atEnd = page.page === page.pages
  return (
    <nav aria-label={label} className="flex flex-wrap items-center gap-x-5 gap-y-3">
      {/* Read out when the page turns: the focus stays on the button pressed, here at the foot of the list. */}
      <p aria-live="polite" className="min-w-0 flex-[1_1_220px] text-lg text-muted-foreground">{line}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <Button variant="outline" aria-disabled={atStart} className={cn(atStart && 'opacity-50')} onClick={() => go(page.page - 1)}>
          <ChevronLeft aria-hidden />
          Înapoi
        </Button>
        {pageNumbers(page.page, page.pages).map((number, index) =>
          number === null ? (
            <span key={`gap-${index}`} aria-hidden className="min-w-7 text-center font-bold text-muted-foreground">…</span>
          ) : (
            <Button
              key={number}
              variant={number === page.page ? 'secondary' : 'outline'}
              aria-current={number === page.page ? 'page' : undefined}
              aria-label={`Pagina ${number}`}
              className="min-w-12 px-3"
              onClick={() => go(number)}
            >
              {number}
            </Button>
          ),
        )}
        <Button variant="outline" aria-disabled={atEnd} className={cn(atEnd && 'opacity-50')} onClick={() => go(page.page + 1)}>
          Înainte
          <ChevronRight aria-hidden />
        </Button>
      </div>
    </nav>
  )
}
