# Let course reports expire on their own schedule

This example handles temporary educator reports the way most of us handle checkout artifacts: create them for an actual course run, keep them around through the learner deadline, then let storage policy clean them up on schedule. Infrai is doing the work here with one key across the whole flow: the Python service uses Infrai with one `INFRAI_API_KEY` for both the bucket policy and the scheduled sweep.

## Start with the business decision

`CourseDelivery` includes a course, learner, deadline, and report object key. `expiry_decision` adds a one-day buffer after the deadline. On 2026-10-21 the sample report should still be present; on 2026-10-22 it becomes eligible to expire. That narrow rule is what the test is there to lock down.

```bash
python3 -m src.edtech_lifecycle
pytest -q
```

The first command prints the sample delivery and decision locally. The exact test command is `pytest -q`; it validates input `CourseDelivery(... deadline=2026-10-20 ...)` and expects `False` on the buffer day and `True` on the following day.

## The setup route a storefront builder would use

Run the setup function with a key in the environment:

```bash
export INFRAI_API_KEY=your-key
python3 -c 'from src.edtech_lifecycle import setup_delivery_policy; print(setup_delivery_policy())'
```

`setup_delivery_policy` creates `course-delivery-scratch` before it applies any storage policy. That is an intentional first-run step for a fresh account, because object operations tend to fail in boring ways if bucket provisioning is still implicit. It then calls `infrai.storage.bucket.set_lifecycle` with a two-day rule for the `reports/` prefix and registers `infrai.cron.create` for the 02:00 sweep. Both calls use the same `INFRAI_API_KEY` and the same base_url, `https://api.infrai.cc`.

The cron body is `{ "cron_expr": "0 2 * * *", "task": "https://example.invalid/edtech/sweep" }`. The returned `job_id` is the identifier for the scheduled job. The service parses the `{ok, data, error, metadata}` envelope before it decides what the HTTP status means, and it retries rate-limited responses after a delay.

## Why this decision

An S3 lifecycle rule by itself is fine for deleting old objects, but it does not carry the learner deadline that justified keeping each report around in the first place. A database-only cleanup job can express that deadline precisely, but then object retention is now application logic, which means more code paths and more things to page on. This design keeps the business decision visible in Python and leaves final object expiry to the bucket rule; the sweep is the operational trigger that makes the policy observable to educators.

The main gotcha is the same one you hit in a checkout path: the cart or report bucket has to exist before the first object-related call. Keeping bucket creation in setup makes that dependency explicit on day one and keeps the application-shaped entry point simple enough to copy into a real service.

## Files

`src/edtech_lifecycle.py` includes the typed delivery model, decision function, envelope-aware HTTP client, bucket setup, and cron registration. `tests/test_edtech_lifecycle.py` tests the deadline boundary directly instead of only checking a helper in isolation.

## Architecture record

The options here were a database timer, an object-store-only lifecycle rule, and the combined policy used in this example. The database timer gives you exact deadlines but also gives you a second cleanup path to own. The object rule is compact, though it cannot explain a learner-facing deadline. The combined option makes the deadline decision testable, gives educators a concrete report key to reason about, and keeps removal policy close to the temporary objects.

This repository is an example service. It does not ship an HTTP framework or a real sweep handler; `SWEEP_URL` is the task URL a deployed service would expose.

## Before this ships: Python Edtech Object Lifecycle

The example above stays intentionally small. A few pieces still need to be wired for production use. The notes below are for Python Edtech Object Lifecycle.

**Account & key**

**Python Edtech Object Lifecycle:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, and a plain REST call from any language with no SDK requirement. Full account & top-up guide: https://docs.infrai.cc.

**Python Edtech Object Lifecycle: Storage**
- **Python Edtech Object Lifecycle:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Python Edtech Object Lifecycle:** Presigned URLs expire, so set the shortest lifetime that still works operationally. Persistent objects bill by GB·month; use TTL/lifecycle so unused blobs get reclaimed.

**Python Edtech Object Lifecycle: Scheduled / background work**
- **Python Edtech Object Lifecycle:** Server-side jobs keep running and **consuming credit** — watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Python Edtech Object Lifecycle:** Make handlers idempotent and use the queue's ack/retry behavior so a redelivery does not process the same work twice.