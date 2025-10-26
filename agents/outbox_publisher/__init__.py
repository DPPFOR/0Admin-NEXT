"""Outbox publisher worker v1.

Publishes events from event_outbox via pluggable transports (stdout/webhook),
with strict leasing and backoff/DLQ policy.
"""

