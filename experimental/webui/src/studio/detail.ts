/* How much of the loop the page shows: everything (`full`), or only what a person judging the employee needs
   (`simple`: no diagnosis, selection, lookups, Harness map, inspector, ledger or audit). The person's choice is kept
   in the browser; a link may set it with ?view=simple or ?view=full. Full until chosen otherwise. */

export type Detail = 'simple' | 'full'

const CHOICE = 'studio.detail'

function chosen(): Detail {
  try {
    const asked = new URLSearchParams(location.search).get('view')
    if (asked === 'simple' || asked === 'full') localStorage.setItem(CHOICE, asked)
    return localStorage.getItem(CHOICE) === 'simple' ? 'simple' : 'full'
  } catch {
    // Storage can be blocked; the full page shows then.
    return 'full'
  }
}

export const detail: Detail = chosen()

/** Keep the person's choice and load the page again with it. */
export function switchDetail(next: Detail): void {
  localStorage.setItem(CHOICE, next)
  location.reload()
}
