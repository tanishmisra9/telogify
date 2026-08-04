import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Skeleton } from '@/components/Skeleton'
import { StatusLink, StatusPage } from '@/components/StatusPage'
import { apiPost } from '@/lib/api'

type Result = 'checking' | 'confirmed' | 'already_confirmed' | 'expired' | 'invalid' | 'error'

export function VerifyPage() {
  const [params] = useSearchParams()
  const token = params.get('t') ?? ''
  const [result, setResult] = useState<Result>('checking')
  // React 19 StrictMode invokes effects twice in dev. The token is single-use, so a second POST
  // would confirm on the first call and report "invalid" on the second, which is exactly the
  // state a real reader must never be shown.
  const sent = useRef(false)

  useEffect(() => {
    if (sent.current) return
    sent.current = true

    if (!token) {
      setResult('invalid')
      return
    }
    // Confirmation is a POST, so a mail scanner following the link with a GET cannot opt anyone
    // in on the reader's behalf.
    apiPost<{ status: Result }>('/subscribe/verify', { token })
      .then((res) => setResult(res.status))
      .catch(() => setResult('error'))
  }, [token])

  if (result === 'checking') {
    return (
      <StatusPage marker="Checking" heading="Confirming your seat.">
        <Skeleton className="h-5 w-64" />
      </StatusPage>
    )
  }

  if (result === 'confirmed' || result === 'already_confirmed') {
    const isNew = result === 'confirmed'
    return (
      <StatusPage
        marker={isNew ? 'Confirmed' : 'Already on the grid'}
        heading={isNew ? 'You are on the grid.' : 'You are already in.'}
        actions={
          <>
            <StatusLink to="/weekends" variant="primary">
              See the latest weekend
            </StatusLink>
            <StatusLink to="/">Go home</StatusLink>
          </>
        }
      >
        {isNew
          ? 'Three insights land in your inbox after every race weekend, built from the session telemetry rather than the broadcast.'
          : 'This address was already confirmed, so there is nothing more to do.'}
      </StatusPage>
    )
  }

  if (result === 'expired') {
    return (
      <StatusPage
        marker="Link expired"
        heading="That link timed out."
        actions={
          <StatusLink to="/subscribe" variant="primary">
            Try again
          </StatusLink>
        }
      >
        Confirmation links are good for 24 hours. Enter your address again and we will send a
        fresh one.
      </StatusPage>
    )
  }

  if (result === 'error') {
    return (
      <StatusPage
        marker="Error"
        heading="Something went wrong."
        actions={
          <StatusLink to="/subscribe" variant="primary">
            Back to signup
          </StatusLink>
        }
      >
        We could not confirm your address just now. Try the link again in a moment.
      </StatusPage>
    )
  }

  return (
    <StatusPage
      marker="Invalid link"
      heading="That link does not check out."
      actions={
        <StatusLink to="/subscribe" variant="primary">
          Back to signup
        </StatusLink>
      }
    >
      This confirmation link is not valid, or it has already been used. Signing up again sends a
      fresh one.
    </StatusPage>
  )
}
