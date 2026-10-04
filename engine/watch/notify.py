"""Persistent watched-address alerts and post-publication Resend delivery.

This module consumes the real ``ChangeEvent.affected`` set produced by publication. It never
decides whether a law applies and it never runs before the live rule set has been swapped in.
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import secrets
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from engine.ir import Rule, RuleSet
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv
from engine.rules.render import rule_result

log = logging.getLogger("tenantly.alerts")
NOTIFICATION_TYPE = "published_law_change"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:20]}"


@dataclass(frozen=True)
class Delivery:
    status: str
    provider_message_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class NotificationContent:
    subject: str
    text: str
    html: str


class AlertRepository:
    """Small SQLite store; address details remain in Tenantly's existing resolved dataset."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _init(self) -> None:
        with self._connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS watched_addresses (
                    id TEXT PRIMARY KEY,
                    address_id TEXT NOT NULL,
                    normalized_property_id TEXT NOT NULL,
                    email TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    unsubscribe_token TEXT NOT NULL UNIQUE,
                    last_notified_change_id TEXT,
                    UNIQUE(address_id, email)
                );
                CREATE TABLE IF NOT EXISTS notification_events (
                    id TEXT PRIMARY KEY,
                    watched_address_id TEXT NOT NULL REFERENCES watched_addresses(id),
                    change_id TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    attempted_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('sent', 'failed')),
                    provider_message_id TEXT,
                    error_message TEXT,
                    UNIQUE(watched_address_id, change_id, notification_type)
                );
                CREATE INDEX IF NOT EXISTS watched_addresses_address_active
                    ON watched_addresses(address_id, active);
                CREATE INDEX IF NOT EXISTS notification_events_watch_time
                    ON notification_events(watched_address_id, attempted_at DESC);
                """
            )

    def subscribe(self, address_id: str, email: str, lang: str) -> tuple[dict, bool]:
        normalized_email = email.strip().lower()
        with self.lock, self._connect() as con:
            row = con.execute(
                "SELECT * FROM watched_addresses WHERE address_id = ? AND email = ?",
                (address_id, normalized_email),
            ).fetchone()
            if row:
                con.execute(
                    "UPDATE watched_addresses SET active = 1, lang = ? WHERE id = ?",
                    (lang, row["id"]),
                )
                return dict(row) | {"active": 1, "lang": lang}, False
            created = now_iso()
            watched_id = _id("watch", address_id, normalized_email)
            token = secrets.token_urlsafe(32)
            con.execute(
                """
                INSERT INTO watched_addresses
                    (id, address_id, normalized_property_id, email, lang, created_at, active,
                     unsubscribe_token)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?)
                """,
                (watched_id, address_id, address_id, normalized_email, lang, created, token),
            )
            return {
                "id": watched_id,
                "address_id": address_id,
                "normalized_property_id": address_id,
                "email": normalized_email,
                "lang": lang,
                "created_at": created,
                "active": 1,
                "unsubscribe_token": token,
                "last_notified_change_id": None,
            }, True

    def unsubscribe(self, token: str) -> bool:
        with self.lock, self._connect() as con:
            cur = con.execute(
                """
                UPDATE watched_addresses SET active = 0
                WHERE unsubscribe_token = ? AND active = 1
                """,
                (token,),
            )
            return cur.rowcount > 0

    def by_token(self, token: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT * FROM watched_addresses WHERE unsubscribe_token = ?", (token,)
            ).fetchone()
            return dict(row) if row else None

    def active_for(self, address_ids: list[str]) -> list[dict]:
        if not address_ids:
            return []
        marks = ",".join("?" for _ in address_ids)
        with self._connect() as con:
            rows = con.execute(
                f"SELECT * FROM watched_addresses WHERE active = 1 AND address_id IN ({marks})",
                address_ids,
            ).fetchall()
            return [dict(row) for row in rows]

    def last_event(self, watched_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                """
                SELECT * FROM notification_events
                WHERE watched_address_id = ?
                ORDER BY attempted_at DESC, id DESC LIMIT 1
                """,
                (watched_id,),
            ).fetchone()
            return dict(row) if row else None

    def deliver_once(
        self,
        watcher: dict,
        change_id: str,
        notification_type: str,
        send: Callable[[], Delivery],
    ) -> tuple[dict, bool]:
        """Run one provider attempt under the uniqueness transaction.

        Holding this small transaction through the provider call prevents two publication workers
        from sending the same email. A completed failure is also idempotent on process restart.
        """
        event_id = _id("notice", watcher["id"], change_id, notification_type)
        with self.lock, self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            existing = con.execute(
                """
                SELECT * FROM notification_events
                WHERE watched_address_id = ? AND change_id = ? AND notification_type = ?
                """,
                (watcher["id"], change_id, notification_type),
            ).fetchone()
            if existing:
                con.commit()
                return dict(existing), False
            attempted = now_iso()
            try:
                delivery = send()
            except Exception as exc:  # noqa: BLE001 - delivery failure must be audited, not raised
                delivery = Delivery("failed", error_message=f"{type(exc).__name__}: {exc}"[:500])
            con.execute(
                """
                INSERT INTO notification_events
                    (id, watched_address_id, change_id, notification_type, recipient_email,
                     attempted_at, provider, status, provider_message_id, error_message)
                VALUES (?, ?, ?, ?, ?, ?, 'resend', ?, ?, ?)
                """,
                (
                    event_id,
                    watcher["id"],
                    change_id,
                    notification_type,
                    watcher["email"],
                    attempted,
                    delivery.status,
                    delivery.provider_message_id,
                    delivery.error_message,
                ),
            )
            if delivery.status == "sent":
                con.execute(
                    "UPDATE watched_addresses SET last_notified_change_id = ? WHERE id = ?",
                    (change_id, watcher["id"]),
                )
            con.commit()
            event = con.execute(
                "SELECT * FROM notification_events WHERE id = ?", (event_id,)
            ).fetchone()
            return dict(event), True


class ResendClient:
    def __init__(self, api_key: str, from_email: str) -> None:
        self.api_key = api_key.strip()
        self.from_email = from_email.strip()

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.from_email)

    def send(self, recipient: str, content: NotificationContent) -> Delivery:
        if not self.configured:
            return Delivery("failed", error_message="Email notifications are not configured.")
        body = json.dumps(
            {
                "from": self.from_email,
                "to": [recipient],
                "subject": content.subject,
                "text": content.text,
                "html": content.html,
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Tenantly/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            message_id = payload.get("id")
            if not message_id:
                return Delivery("failed", error_message="Resend returned no message id.")
            return Delivery("sent", provider_message_id=str(message_id))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:400]
            return Delivery("failed", error_message=f"Resend HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return Delivery("failed", error_message=f"Resend request failed: {exc}"[:500])


class AlertService:
    def __init__(
        self,
        repository: AlertRepository,
        resend: ResendClient,
        public_app_url: str,
    ) -> None:
        self.repository = repository
        self.resend = resend
        self.public_app_url = public_app_url.rstrip("/")

    @property
    def configured(self) -> bool:
        return self.resend.configured

    def subscribe(self, address_id: str, email: str, lang: str) -> dict:
        watcher, created = self.repository.subscribe(address_id, email, lang)
        if created and self.configured:
            try:
                self._send_confirmation(watcher)
            except Exception:  # noqa: BLE001
                log.exception("confirmation email failed watch=%s", watcher["id"])
        return {
            "subscription_id": watcher["id"],
            "unsubscribe_token": watcher["unsubscribe_token"],
            "address_id": watcher["address_id"],
            "created_at": watcher["created_at"],
            "active": bool(watcher["active"]),
            "created": created,
            "notifications_configured": self.configured,
            "feeds": {
                "atom": f"/v1/alerts/feed/{address_id}.atom",
                "ics": f"/v1/alerts/calendar/{address_id}.ics",
            },
        }

    def _send_confirmation(self, watcher: dict) -> None:
        address_url = f"{self.public_app_url}/a/{urllib.parse.quote(watcher['address_id'])}"
        unsubscribe_url = (
            f"{self.public_app_url}/v1/alerts/unsubscribe?token="
            f"{urllib.parse.quote(watcher['unsubscribe_token'])}"
        )
        subject = "You're watching this address on Tenantly"
        text = (
            f"You've subscribed to housing-law alerts for address {watcher['address_id']}.\n\n"
            f"We'll email you whenever a verified law change affects this property.\n\n"
            f"View property: {address_url}\n\n"
            f"Unsubscribe: {unsubscribe_url}\n\n"
            "Tenantly provides public legal information, not legal advice."
        )
        html_body = (
            "<p><strong>You're now watching this address on Tenantly.</strong></p>"
            "<p>We'll email you whenever a verified housing-law change affects this property.</p>"
            f"<p><a href=\"{html.escape(address_url)}\">View property analysis</a></p>"
            f"<p><small><a href=\"{html.escape(unsubscribe_url)}\">Unsubscribe</a> · "
            "Tenantly provides public legal information, not legal advice.</small></p>"
        )
        content = NotificationContent(subject, text, html_body)
        delivery = self.resend.send(watcher["email"], content)
        if delivery.status != "sent":
            log.warning("confirmation email failed watch=%s error=%s", watcher["id"], delivery.error_message)

    def status(self, token: str) -> dict | None:
        watcher = self.repository.by_token(token)
        if not watcher:
            return None
        event = self.repository.last_event(watcher["id"])
        return {
            "subscription_id": watcher["id"],
            "address_id": watcher["address_id"],
            "created_at": watcher["created_at"],
            "active": bool(watcher["active"]),
            "notifications_configured": self.configured,
            "last_notification": (
                {
                    "change_id": event["change_id"],
                    "attempted_at": event["attempted_at"],
                    "provider": event["provider"],
                    "status": event["status"],
                    "provider_message_id": event["provider_message_id"],
                    "error_message": event["error_message"],
                }
                if event
                else None
            ),
        }

    def notify_published_change(
        self,
        change: dict,
        records: dict[str, dict],
        before: RuleSet,
        after: RuleSet,
    ) -> dict:
        affected_by_id = {item["address_id"]: item for item in change["affected"]}
        watchers = self.repository.active_for(list(affected_by_id))
        sent = failed = skipped = 0
        for watcher in watchers:
            affected = affected_by_id[watcher["address_id"]]
            content = build_content(
                watcher,
                records[watcher["address_id"]],
                affected,
                change,
                before,
                after,
                self.public_app_url,
            )
            event, attempted = self.repository.deliver_once(
                watcher,
                change["change_id"],
                NOTIFICATION_TYPE,
                lambda w=watcher, c=content: self.resend.send(w["email"], c),
            )
            if not attempted:
                skipped += 1
            elif event["status"] == "sent":
                sent += 1
            else:
                failed += 1
                log.warning(
                    "notification failed watch=%s change=%s error=%s",
                    watcher["id"],
                    change["change_id"],
                    event["error_message"],
                )
        return {
            "matched_watchers": len(watchers),
            "sent": sent,
            "failed": failed,
            "skipped_duplicate": skipped,
            "configured": self.configured,
        }


def _describe(rule: Rule | None, result: str) -> str:
    if rule is None or result == "none":
        return "No result from this rule."
    values = "; ".join(k.text for k in rule.key_values if k.text)
    detail = values or rule.requirement
    return f"{rule.title} ({result}): {detail}"


def build_content(
    watcher: dict,
    record: dict,
    affected: dict,
    change: dict,
    before: RuleSet,
    after: RuleSet,
    public_app_url: str,
) -> NotificationContent:
    """Build legal-change text only from the published diff, engine outcome and verified rule IR."""
    before_rules = {r.rule_id: r for r in before.rules}
    after_rules = {r.rule_id: r for r in after.rules}
    before_results = {item["rule_id"]: item["result"] for item in affected["before"]}
    after_results = {item["rule_id"]: item["result"] for item in affected["after"]}
    changed_ids = [
        rule_id
        for rule_id in dict.fromkeys([*before_results, *after_results])
        if before_results.get(rule_id, "none") != after_results.get(rule_id, "none")
    ]
    primary_id = next(
        (rule_id for rule_id in changed_ids if after_results.get(rule_id, "none") != "none"),
        changed_ids[0],
    )
    primary = after_rules.get(primary_id) or before_rules.get(primary_id)
    on = (
        change["compare"].get("on")
        or change["compare"].get("after")
        or change["created_at"][:10]
    )
    outcome = evaluate_address(after, record, AddressEnv(record), datetime.fromisoformat(on).date())
    titles = {r.rule_id: r.title for r in after.rules}
    rendered = {
        item.rule_id: rule_result(item, datetime.fromisoformat(on).date(), titles)
        for item in outcome.outcomes
    }
    reason = rendered.get(primary_id, {}).get("reason", {}).get("en")
    why = reason or (
        primary.coverage_text
        if primary
        else "The published impact analysis includes this property."
    )
    before_text = "\n".join(
        f"- {_describe(before_rules.get(rule_id), before_results.get(rule_id, 'none'))}"
        for rule_id in changed_ids
    )
    after_text = "\n".join(
        f"- {_describe(after_rules.get(rule_id), after_results.get(rule_id, 'none'))}"
        for rule_id in changed_ids
    )
    transitions = ", ".join(
        f"{rule_id}: {before_results.get(rule_id, 'none')} → {after_results.get(rule_id, 'none')}"
        for rule_id in changed_ids
    )
    effective = primary.effective.output() if primary else None
    jurisdiction = (
        primary.jurisdiction.label
        if primary
        else (affected.get("legal_city") or record["state"])
    )
    citation = primary.citation.cite if primary else "Source unavailable"
    source_url = primary.citation.url if primary else ""
    analysis_url = (
        f"{public_app_url}/a/{urllib.parse.quote(watcher['address_id'])}"
        f"?asOf={urllib.parse.quote(on)}"
    )
    subject = "Housing law change affecting your property"
    text = (
        "A published housing-law change may affect your property.\n\n"
        f"Property:\n{affected['label']}\n\n"
        f"What changed:\n{change['title']}\n{transitions}\n\n"
        f"Before:\n{before_text}\n\nAfter:\n{after_text}\n\n"
        f"Effective date:\n{effective or 'Not stated in the verified source'}\n\n"
        f"Jurisdiction:\n{jurisdiction}\n\n"
        f"Why this property is affected:\n{why}\n\n"
        f"Source:\n{citation}\n{source_url}\n\n"
        f"View full analysis:\n{analysis_url}\n\n"
        "Tenantly provides public legal information, not legal advice. Check the official source "
        "or a qualified professional before acting."
    )
    rows = [
        ("Property", affected["label"]),
        ("What changed", f"{change['title']} — {transitions}"),
        ("Before", before_text),
        ("After", after_text),
        ("Effective date", effective or "Not stated in the verified source"),
        ("Jurisdiction", jurisdiction),
        ("Why this property is affected", why),
        ("Source", f"{citation}\n{source_url}"),
    ]
    html_rows = "".join(
        f"<h3>{html.escape(label)}</h3><p>{html.escape(value).replace(chr(10), '<br>')}</p>"
        for label, value in rows
    )
    html_body = (
        "<p><strong>A published housing-law change may affect your property.</strong></p>"
        f"{html_rows}<p><a href=\"{html.escape(analysis_url)}\">View Full Analysis</a></p>"
        "<p><small>Tenantly provides public legal information, not legal advice. Check the "
        "official source or a qualified professional before acting.</small></p>"
    )
    return NotificationContent(subject, text, html_body)
