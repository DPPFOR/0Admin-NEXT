# Outbox Overview

The outbox provides a durable queue for domain events that must be delivered to downstream systems. Events are inserted atomically with domain state changes and consumed by a lightweight worker that invokes topic-specific handlers.

## Schema

- Schema: `outbox`
- Table: `events`
  - `id UUID PRIMARY KEY`
  - `topic TEXT NOT NULL`
  - `payload JSONB NOT NULL`
  - `status TEXT NOT NULL DEFAULT 'pending'`
  - `attempt_count INT NOT NULL DEFAULT 0`
  - `next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT `timezone('utc', now())``
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT `timezone('utc', now())``
- Indexes:
  - `(status, next_attempt_at)` for polling by worker
  - `(topic, status)` for analytics / monitoring

## Status Lifecycle

```
pending → processing → processed
          ↘ (handler error) pending (attempt+1, next_attempt+backoff)
```

- **pending** – ready for dispatch once `next_attempt_at <= now()`.
- **processing** – leased by a consumer.
- **processed** – successfully handled.
- **failed** – reserved for future terminal state (not yet emitted by the minimal consumer).

## Backoff & Limits

- Initial attempt scheduled at `next_attempt_at = now() + delay_s` (defaults to zero).
- On handler failure or missing handler the consumer increments `attempt_count` and reschedules after `60s * (attempt_count + 1)`.
- Payloads must be JSON-serialisable mappings; non-serialisable data is rejected at enqueue time.
- Logging is JSON-structured and intentionally omits payload contents to avoid PII exposure.

## Example Usage

```python
from backend.core.outbox.publisher import enqueue_event

event_id = enqueue_event(
    "InboxItemAnalysisReady",
    {"tenant_id": "00000000-0000-0000-0000-000000000000", "item_id": "42"},
)
print("enqueued", event_id)
```

Consume a single pending event from the CLI:

```bash
python tools/flows/outbox_consume_one.py
```

Run the focused test suite (DB tests require `RUN_DB_TESTS=1` and a reachable Postgres specified via `DATABASE_URL` or `OUTBOX_DB_URL`):

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/outbox/test_outbox_publisher.py
RUN_DB_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q tests/outbox/test_outbox_db.py
```
