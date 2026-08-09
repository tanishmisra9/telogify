import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { LoadingSwap } from '@/components/LoadingSwap'
import {
  CheckingPlaceholder,
  StatusButton,
  StatusContent,
  StatusLink,
  StatusShell,
} from '@/components/StatusPage'
import { apiPost } from '@/lib/api'

type Result =
  | 'working'
  | 'unsubscribed'
  | 'already_unsubscribed'
  | 'resubscribed'
  | 'invalid'
  | 'error'

export function UnsubscribePage() {
  const [params] = useSearchParams()
  const token = params.get('t') ?? ''
  const [result, setResult] = useState<Result>('working')
  const [rejoining, setRejoining] = useState(false)
  const sent = useRef(false)

  useEffect(() => {
    if (sent.current) return
    sent.current = true

    if (!token) {
      setResult('invalid')
      return
    }
    // Unsubscribes on arrival rather than asking for a confirming click. Someone who clicked
    // Unsubscribe has already stated their intent, and making them state it twice is the kind
    // of friction that gets a sender marked as spam instead. The misclick case is covered by
    // the one-tap rejoin below.
    apiPost<{ status: Result }>(`/unsubscribe?t=${encodeURIComponent(token)}`)
      .then((res) => setResult(res.status))
      .catch(() => setResult('error'))
  }, [token])

  function rejoin() {
    setRejoining(true)
    apiPost<{ status: Result }>(`/subscribe/resubscribe?t=${encodeURIComponent(token)}`)
      .then((res) => setResult(res.status))
      .catch(() => setResult('error'))
      .finally(() => setRejoining(false))
  }

  let content: React.ReactNode = null

  if (result === 'unsubscribed' || result === 'already_unsubscribed') {
    content = (
      <StatusContent
        marker="Unsubscribed"
        heading="You have left the grid."
        actions={
          <>
            <StatusButton onClick={rejoin} disabled={rejoining}>
              {rejoining ? 'Rejoining...' : 'Rejoin the grid'}
            </StatusButton>
            <StatusLink to="/">Go home</StatusLink>
          </>
        }
      >
        No more digests will reach this address. If that was a misclick, one tap puts you back on
        without another confirmation email.
      </StatusContent>
    )
  } else if (result === 'resubscribed') {
    content = (
      <StatusContent
        marker="Back on the grid"
        heading="Welcome back."
        actions={
          <>
            <StatusLink to="/weekends" variant="primary">
              See the latest weekend
            </StatusLink>
            <StatusLink to="/">Go home</StatusLink>
          </>
        }
      >
        Your seat is restored. The next digest lands after the next race weekend.
      </StatusContent>
    )
  } else if (result === 'error') {
    content = (
      <StatusContent marker="Error" heading="Something went wrong." actions={<StatusLink to="/">Go home</StatusLink>}>
        We could not update your subscription just now. Try the link again in a moment.
      </StatusContent>
    )
  } else if (result !== 'working') {
    // 'working' falls through with content still null; LoadingSwap shows the placeholder
    // instead and never renders `content` while loading.
    // Two genuinely different situations, and telling someone their code is "missing" when they
    // can see it in the address bar reads as the site being broken rather than the link being bad.
    // No token at all is the older-digest case; a token that fails to verify is a bad link.
    content = token ? (
      <StatusContent
        marker="Invalid link"
        heading="That link does not check out."
        actions={<StatusLink to="/">Go home</StatusLink>}
      >
        This unsubscribe link is not valid. Use the Unsubscribe link at the bottom of any recent
        Telogify email and it will work.
      </StatusContent>
    ) : (
      <StatusContent
        marker="Missing code"
        heading="This link is missing its code."
        actions={<StatusLink to="/">Go home</StatusLink>}
      >
        Use the Unsubscribe link at the bottom of any recent Telogify email and it will work.
      </StatusContent>
    )
  }

  return (
    <StatusShell>
      <LoadingSwap
        loading={result === 'working'}
        placeholder={<CheckingPlaceholder heading="Taking you off the list." />}
      >
        {content}
      </LoadingSwap>
    </StatusShell>
  )
}
