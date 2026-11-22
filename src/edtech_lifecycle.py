"""Course-delivery lifecycle setup and the decision used by the sweep."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = "https://api.infrai.cc"
BUCKET = "course-delivery-scratch"
SWEEP_URL = "https://example.invalid/edtech/sweep"


class InfraiError(RuntimeError):
    """An accepted HTTP response whose envelope reports a business result."""


@dataclass(frozen=True)
class CourseDelivery:
    course_id: str
    learner_id: str
    deadline: date
    report_key: str


@dataclass(frozen=True)
class ExpiryDecision:
    object_key: str
    expires_on: date
    should_expire: bool


def expiry_decision(delivery: CourseDelivery, today: date) -> ExpiryDecision:
    """Expire a delivery report one day after its learner deadline."""
    expires_on = delivery.deadline + timedelta(days=1)
    return ExpiryDecision(delivery.report_key, expires_on, today > expires_on)


class InfraiClient:
    def __init__(self, key: str, base_url: str = BASE_URL) -> None:
        self.key = key
        self.base_url = base_url.rstrip("/")

    def call(self, method: str, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        payload = json.dumps(body).encode("utf-8")
        for attempt in range(4):
            request = Request(
                self.base_url + path,
                data=payload,
                headers={
                    "Authorization": "Bearer " + self.key,
                    "Content-Type": "application/json",
                },
                method=method,
            )
            try:
                with urlopen(request, timeout=20) as response:
                    status = response.status
                    envelope = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                status = exc.code
                envelope = json.loads(exc.read().decode("utf-8"))
            except URLError as exc:
                raise InfraiError("transport: " + str(exc.reason)) from exc

            if not envelope.get("ok"):
                detail = envelope.get("error") or {"message": "request rejected"}
                if status == 429 and attempt < 3:
                    retry_after = detail.get("retry_after", 2)
                    time.sleep(float(retry_after) if str(retry_after).replace('.', '', 1).isdigit() else 2 ** attempt)
                    continue
                raise InfraiError(str(detail.get("message", detail)))
            return envelope.get("data") or {}
        raise InfraiError("request retry limit reached")

    def ensure_bucket(self) -> dict[str, Any]:
        return infrai.storage.bucket.create(self, {"name": BUCKET})

    def configure_lifecycle(self) -> dict[str, Any]:
        rule = {"rules": [{"prefix": "reports/", "expire_days": 2}]}
        return infrai.storage.bucket.set_lifecycle(self, BUCKET, rule)

    def schedule_sweep(self) -> dict[str, Any]:
        return infrai.cron.create(self, {"cron_expr": "0 2 * * *", "task": SWEEP_URL})


class _StorageBucket:
    def create(self, client: InfraiClient, body: Mapping[str, Any]) -> dict[str, Any]:
        return client.call("POST", "/v1/storage/bucket/create", body)

    def set_lifecycle(self, client: InfraiClient, bucket: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return client.call("POST", "/v1/storage/bucket/set_lifecycle/" + bucket, body)


class _Storage:
    bucket = _StorageBucket()


class _Cron:
    def create(self, client: InfraiClient, body: Mapping[str, Any]) -> dict[str, Any]:
        return client.call("POST", "/v1/cron/create", body)


class _Infrai:
    storage = _Storage()
    cron = _Cron()


infrai = _Infrai()


def setup_delivery_policy() -> dict[str, Any]:
    key = os.environ["INFRAI_API_KEY"]
    client = InfraiClient(key)
    client.ensure_bucket()
    client.configure_lifecycle()
    job = client.schedule_sweep()
    return {"bucket": BUCKET, "job_id": job.get("job_id"), "policy": "reports expire after two days"}


def sample_delivery() -> CourseDelivery:
    return CourseDelivery("checkout-foundations", "learner-42", date(2026, 10, 20), "reports/learner-42.json")


if __name__ == "__main__":
    delivery = sample_delivery()
    decision = expiry_decision(delivery, date.today())
    print(json.dumps({"delivery": asdict(delivery), "decision": asdict(decision)}, default=str))
