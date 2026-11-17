/**
 * Brings the start of a list to the top of the window after its page changed, below the bar at the
 * top of the page while that bar stays in place. The bar is taller when a narrow window wraps it,
 * so its height is measured each time.
 */
export function scrollBelowHeader(element: HTMLElement | null): void {
  if (!element) return
  const header = document.querySelector('header')
  const sticks = header && ['sticky', 'fixed'].includes(getComputedStyle(header).position)
  const covered = sticks ? header.getBoundingClientRect().height : 0
  window.scrollTo({ top: window.scrollY + element.getBoundingClientRect().top - covered - 16 })
}
