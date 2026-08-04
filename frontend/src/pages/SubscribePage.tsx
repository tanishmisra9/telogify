import { useEffect, useRef, useState, type FormEvent } from 'react'
import { BackHomeButton } from '@/components/BackHomeButton'
import { BlurFade } from '@/components/BlurFade'
import { apiPost } from '@/lib/api'
import { loadRecaptcha, recaptchaEnabled, recaptchaToken } from '@/lib/recaptcha'

type Status = 'idle' | 'submitting' | 'done' | 'invalid' | 'throttled' | 'error'

const ERROR_COPY: Partial<Record<Status, string>> = {
  invalid: 'That address does not look right. Check it and try again.',
  throttled: 'Too many attempts from here. Give it an hour and try again.',
  error: 'Something went wrong at our end. Try again in a moment.',
}

export function SubscribePage() {
  const [email, setEmail] = useState('')
  const [status, setStatus] = useState<Status>('idle')
  // Honeypot. Named like a field a form-filling bot expects to find, kept out of the tab order
  // and out of the accessibility tree so no real user ever meets it.
  const [company, setCompany] = useState('')
  const doneRef = useRef<HTMLParagraphElement>(null)

  useEffect(() => {
    loadRecaptcha()
  }, [])

  // Focus moves to the confirmation when the form is replaced, or a screen reader user is left
  // on a control that no longer exists with no idea anything happened.
  useEffect(() => {
    if (status === 'done') doneRef.current?.focus()
  }, [status])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (status === 'submitting') return
    if (company) {
      // Silently accept: telling a bot it was caught just teaches it what to avoid.
      setStatus('done')
      return
    }
    setStatus('submitting')
    try {
      await apiPost<{ status: string }>('/subscribe', {
        email,
        recaptcha_token: await recaptchaToken(),
      })
      setStatus('done')
    } catch (err) {
      const code = err instanceof Error ? err.message : ''
      setStatus(code === '422' ? 'invalid' : code === '429' ? 'throttled' : 'error')
    }
  }

  const errorMessage = ERROR_COPY[status]

  return (
    // Outer container matches every other page so the heading's left edge lines up
    // sitewide; the lg cap keeps the content itself at a comfortable reading width.
    <main className="mx-auto max-w-[1312px] px-6 py-24">
      {/* The heading sits outside the reading-width cap below. At 86.4px the wordmark line
          measures 854px, so the 672px cap was breaking it across two lines with most of the
          page still empty beside it. A max-width exists to hold body copy to a comfortable
          measure, which a one-line display heading does not need. */}
      <BlurFade>
        <div className="mb-6">
          <BackHomeButton />
        </div>
        {/* 0.9x text-7xl/text-8xl -- the same scale factor applied to the Weekends/Season
            headings, so this stays one ramp step above them exactly as it did before. */}
        <h1 className="select-none font-display text-[4.05rem] leading-[1.05] tracking-tight sm:text-[5.4rem]">
          Telo<span className="text-accent">gify</span> your weekend
        </h1>
      </BlurFade>

      <div className="max-w-2xl">
        <BlurFade>
          <p className="mt-4 text-lg text-muted">
            Three insights per race weekend, speeding to your inbox.
          </p>
        </BlurFade>

        {/* Deliberately not wrapped in a .glass card. The form is the page's one action, and a
            panel around it would read as a widget dropped onto the page rather than the page
            itself asking. Matches the form this replaced. */}
        <BlurFade delay={0.06}>
          <div aria-live="polite" aria-atomic="true" className="mt-12">
            {status === 'done' ? (
              <div className="glass rounded-panel p-7 sm:p-8">
                <p className="kicker text-accent">Check your inbox</p>
                <p
                  ref={doneRef}
                  tabIndex={-1}
                  className="mt-3 font-display text-3xl leading-tight tracking-tight text-ink outline-none"
                >
                  Provisional grid slot held.
                </p>
                <p className="mt-3 text-muted">
                  We sent a confirmation link to {email || 'your inbox'}. Click it and your seat
                  is locked in. The link is good for 24 hours.
                </p>
              </div>
            ) : (
              <form onSubmit={onSubmit} noValidate>
                <label htmlFor="email" className="kicker block text-muted">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  name="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-describedby={errorMessage ? 'subscribe-error' : undefined}
                  aria-invalid={status === 'invalid' || undefined}
                  placeholder="you@example.com"
                  className="mt-2 w-full rounded-panel border-[1.5px] border-ink bg-surface px-4 py-3 text-ink outline-none transition-shadow placeholder:text-muted focus-visible:shadow-[3px_3px_0_var(--color-accent)]"
                />

                {/* Off-screen rather than display:none so a naive bot still fills it. */}
                <div aria-hidden="true" className="absolute left-[-9999px] h-px w-px overflow-hidden">
                  <label htmlFor="company">Company</label>
                  <input
                    id="company"
                    name="company"
                    type="text"
                    tabIndex={-1}
                    autoComplete="off"
                    value={company}
                    onChange={(e) => setCompany(e.target.value)}
                  />
                </div>

                <button
                  type="submit"
                  disabled={status === 'submitting'}
                  className="lift mt-5 w-full rounded-panel border-[1.5px] border-ink bg-accent px-6 py-3 font-display text-2xl text-accent-ink shadow-[4px_4px_0_var(--color-shadow)] outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-4 focus-visible:ring-offset-bg disabled:opacity-60 sm:w-auto"
                >
                  {status === 'submitting' ? 'Checking...' : 'Join the grid'}
                </button>

                {errorMessage && (
                  <p id="subscribe-error" role="alert" className="mt-4 text-sm text-accent">
                    {errorMessage}
                  </p>
                )}

                <p className="mt-6 text-xs leading-relaxed text-muted">
                  No spam, one email per race weekend, unsubscribe in one click.
                  {recaptchaEnabled && (
                    <>
                      {' '}
                      Protected by reCAPTCHA, so Google&apos;s{' '}
                      <a
                        href="https://policies.google.com/privacy"
                        className="underline"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Privacy Policy
                      </a>{' '}
                      and{' '}
                      <a
                        href="https://policies.google.com/terms"
                        className="underline"
                        target="_blank"
                        rel="noreferrer"
                      >
                        Terms of Service
                      </a>{' '}
                      apply.
                    </>
                  )}
                </p>
              </form>
            )}
          </div>
        </BlurFade>
      </div>
    </main>
  )
}
