// reCAPTCHA v3, loaded on the subscribe page only rather than from index.html. The rest of the
// site loads no third-party JS at all, and a marketing page is not a reason to put Google on
// every route a reader visits.
//
// With no site key configured (local dev), every function here no-ops and the backend skips
// verification to match, so the form still works end to end without credentials.

const SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY ?? ''
const SCRIPT_ID = 'recaptcha-v3'

// Must match RECAPTCHA_ACTION in backend/telogify/subscriptions.py: the backend rejects a token
// minted for any other action, so a token lifted from a different page cannot be replayed here.
export const RECAPTCHA_ACTION = 'subscribe'

export const recaptchaEnabled = Boolean(SITE_KEY)

declare global {
  interface Window {
    grecaptcha?: {
      ready: (cb: () => void) => void
      execute: (siteKey: string, opts: { action: string }) => Promise<string>
    }
  }
}

/** Injects the script once. Safe to call on every mount. */
export function loadRecaptcha(): void {
  if (!SITE_KEY || document.getElementById(SCRIPT_ID)) return
  const script = document.createElement('script')
  script.id = SCRIPT_ID
  script.src = `https://www.google.com/recaptcha/api.js?render=${SITE_KEY}`
  script.async = true
  document.head.appendChild(script)
}

/** A fresh token, or '' when reCAPTCHA is not configured or not ready yet. */
export async function recaptchaToken(): Promise<string> {
  if (!SITE_KEY || !window.grecaptcha) return ''
  try {
    await new Promise<void>((resolve) => window.grecaptcha!.ready(resolve))
    return await window.grecaptcha!.execute(SITE_KEY, { action: RECAPTCHA_ACTION })
  } catch {
    // Let the request go through tokenless; the backend decides, and it fails closed.
    return ''
  }
}
