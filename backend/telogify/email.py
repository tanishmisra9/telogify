"""Post-race email digest via Resend.

`render_email` is pure (testable): the 3 insights in email form, key telemetry number
bolded, a "Read the full analysis" CTA, no tables, em dashes stripped. `send_digest`
sends one message per subscriber so addresses are never shared across recipients.
"""

import html
import re

from sqlmodel import Session
from sqlmodel import select

from telogify.config import settings
from telogify.models import Insight, RaceWeekend, Subscriber
from telogify.serialize import strip_em_dashes

_NUM_RE = re.compile(r"\d[\d.,]*(?:\s?(?:km/h|mph|°C|%|s|km|m))?")
_ACCENT = "#b06f12"  # amber, darkened for contrast on a light email background


def _bold_first_number(escaped_text: str) -> str:
    return _NUM_RE.sub(
        lambda m: f'<strong style="color:{_ACCENT}">{m.group(0)}</strong>',
        escaped_text,
        count=1,
    )


def _clean(text: str) -> str:
    return html.escape(strip_em_dashes(text) or "")


def render_email(weekend: RaceWeekend, insights: list[Insight], base_url: str) -> str:
    cta_url = f"{base_url.rstrip('/')}/weekends/{weekend.year}/{weekend.round}"

    blocks = []
    for ins in insights:
        header = _clean(ins.header)
        body = _bold_first_number(_clean(ins.explanation_email))
        blocks.append(
            f'<div style="margin:0 0 28px 0">'
            f'<h2 style="margin:0 0 8px 0;font-size:18px;line-height:1.3;color:#16171d">{header}</h2>'
            f'<p style="margin:0;font-size:15px;line-height:1.6;color:#44454d">{body}</p>'
            f"</div>"
        )

    return (
        '<div style="background:#f5f5f4;padding:32px 16px;'
        'font-family:-apple-system,system-ui,Segoe UI,Roboto,sans-serif">'
        '<div style="max-width:560px;margin:0 auto;background:#ffffff;'
        'border:1px solid #e7e6e4;border-radius:16px;padding:32px">'
        f'<p style="margin:0 0 4px 0;font-size:13px;color:{_ACCENT};font-weight:600">'
        f"{html.escape(weekend.event_name)}</p>"
        '<p style="margin:0 0 24px 0;font-size:13px;color:#8a8a90">Your 3 insights</p>'
        + "".join(blocks)
        + f'<a href="{html.escape(cta_url)}" '
        'style="display:inline-block;margin-top:8px;padding:11px 18px;'
        f"background:{_ACCENT};color:#ffffff;text-decoration:none;border-radius:10px;"
        'font-size:14px;font-weight:500">Read the full analysis</a>'
        "</div></div>"
    )


def send_digest(year: int, round: int, db: Session, recipients: list[str] | None = None) -> int:
    """Send the digest to subscribers (or `recipients`). Returns the number sent."""
    if not settings.resend_api_key:
        raise RuntimeError("RESEND_API_KEY is not set; cannot send the digest.")

    weekend = db.exec(
        select(RaceWeekend).where(RaceWeekend.year == year, RaceWeekend.round == round)
    ).first()
    if weekend is None:
        raise RuntimeError(f"No weekend found for {year} round {round}.")

    insights = db.exec(
        select(Insight).where(Insight.weekend_id == weekend.id).order_by(Insight.slot)
    ).all()
    if not insights:
        raise RuntimeError("No insights to send. Run `telogify run-weekend` first.")

    if recipients is None:
        recipients = [s.email for s in db.exec(select(Subscriber)).all()]
    if not recipients:
        return 0

    import resend

    resend.api_key = settings.resend_api_key
    html_body = render_email(weekend, insights, settings.web_base_url)
    subject = f"{weekend.event_name}: your 3 insights"

    for email in recipients:
        resend.Emails.send(
            {"from": settings.resend_from, "to": [email], "subject": subject, "html": html_body}
        )
    return len(recipients)
