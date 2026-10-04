from pathlib import Path

from engine.ir import RuleSet
from engine.watch.notify import AlertRepository, AlertService, Delivery
from tests.synth import resolved, rule


class FakeResend:
    configured = True

    def __init__(self) -> None:
        self.calls = 0

    def send(self, recipient, content):
        self.calls += 1
        assert recipient == "renter@example.com"
        assert "A published housing-law change may affect your property" in content.text
        assert "View full analysis" in content.text
        return Delivery("sent", provider_message_id="email-123")


def _change() -> dict:
    return {
        "change_id": "chg-demo",
        "title": "Published test law",
        "created_at": "2026-10-04T10:00:00Z",
        "compare": {"mode": "with_without", "on": "2026-10-01"},
        "affected": [
            {
                "address_id": "A0016",
                "label": "3515 Fillmore St, San Francisco, CA",
                "legal_city": "San Francisco",
                "before": [{"rule_id": "CA-ALG-99", "result": "none"}],
                "after": [{"rule_id": "CA-ALG-99", "result": "applies"}],
                "conflict_flag": False,
            }
        ],
    }


def test_published_change_sends_once_and_persists_audit(tmp_path: Path):
    repository = AlertRepository(tmp_path / "alerts.sqlite3")
    resend = FakeResend()
    service = AlertService(repository, resend, "https://tenantly.example")
    subscription = service.subscribe("A0016", "Renter@Example.com", "en")
    new_rule = rule("CA-ALG-99", "algorithmic_rent_setting", "CA")
    before = RuleSet(data_version="before", compiled_at="x", rules=[])
    after = RuleSet(data_version="after", compiled_at="x", rules=[new_rule])

    first = service.notify_published_change(_change(), resolved(), before, after)
    second = service.notify_published_change(_change(), resolved(), before, after)

    assert first == {
        "matched_watchers": 1,
        "sent": 1,
        "failed": 0,
        "skipped_duplicate": 0,
        "configured": True,
    }
    assert second["sent"] == 0 and second["skipped_duplicate"] == 1
    assert resend.calls == 1
    status = service.status(subscription["unsubscribe_token"])
    assert status["last_notification"]["status"] == "sent"
    assert status["last_notification"]["provider_message_id"] == "email-123"
    assert status["last_notification"]["change_id"] == "chg-demo"


def test_unconfigured_delivery_is_failed_without_raising(tmp_path: Path):
    repository = AlertRepository(tmp_path / "alerts.sqlite3")

    class Unconfigured:
        configured = False

        def send(self, recipient, content):
            return Delivery("failed", error_message="Email notifications are not configured.")

    service = AlertService(repository, Unconfigured(), "http://localhost:5173")
    subscription = service.subscribe("A0016", "renter@example.com", "en")
    new_rule = rule("CA-ALG-99", "algorithmic_rent_setting", "CA")
    before = RuleSet(data_version="before", compiled_at="x", rules=[])
    after = RuleSet(data_version="after", compiled_at="x", rules=[new_rule])

    result = service.notify_published_change(_change(), resolved(), before, after)

    assert result["failed"] == 1 and result["configured"] is False
    status = service.status(subscription["unsubscribe_token"])
    assert status["last_notification"]["status"] == "failed"
    assert status["last_notification"]["error_message"] == (
        "Email notifications are not configured."
    )
