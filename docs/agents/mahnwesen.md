# Mahnwesen Agent Documentation

## Overview

The Mahnwesen Agent is a Flock-based system for automated dunning processes. It handles overdue invoice detection, dunning stage determination, notice composition, and event dispatch with full multi-tenant support.

## Architecture

### Core Components

- **Config**: Tenant-specific configuration management
- **Policies**: Business rules for dunning decisions
- **DTOs**: Type-safe data transfer objects
- **Clients**: Read-API and Outbox integration
- **Playbooks**: Flock-based workflow orchestration
- **Templates**: Jinja2-based notice templates

### Multi-Tenant Support

- Strict tenant isolation via RLS
- Tenant-specific configuration overrides
- Header-based tenant identification (`X-Tenant-Id`)
- Correlation ID tracing

## Configuration

### Environment Variables

```bash
# Tenant-specific overrides
MAHNWESEN_<TENANT_ID>_STAGE_1_THRESHOLD=3
MAHNWESEN_<TENANT_ID>_STAGE_2_THRESHOLD=14
MAHNWESEN_<TENANT_ID>_STAGE_3_THRESHOLD=30
MAHNWESEN_<TENANT_ID>_MIN_AMOUNT_CENTS=100
MAHNWESEN_<TENANT_ID>_GRACE_DAYS=0
MAHNWESEN_<TENANT_ID>_MAX_NOTICES_PER_HOUR=200
MAHNWESEN_<TENANT_ID>_LOCALE=de-DE
MAHNWESEN_<TENANT_ID>_READ_API_URL=http://localhost:8000
MAHNWESEN_<TENANT_ID>_COMPANY_NAME=0Admin
MAHNWESEN_<TENANT_ID>_SUPPORT_EMAIL=support@0admin.com
```

### Default Configuration

```python
DunningConfig(
    tenant_id="<UUID>",
    stage_1_threshold=3,      # days
    stage_2_threshold=14,     # days
    stage_3_threshold=30,     # days
    min_amount_cents=100,     # 1.00 EUR
    grace_days=0,             # days
    max_notices_per_hour=200,
    default_locale="de-DE",
    template_version="v1",
    read_api_timeout=10,      # seconds
    outbox_retry_attempts=10,
    outbox_retry_backoff_base=1,  # seconds
    outbox_retry_backoff_max=60   # seconds
)
```

## Business Rules

### Dunning Stages

1. **Stage 1** (3+ days overdue): Friendly reminder via email
2. **Stage 2** (14+ days overdue): Second notice with dunning fee
3. **Stage 3** (30+ days overdue): Final notice with legal implications

### Dunning Fees

- Stage 1: 2.50 EUR
- Stage 2: 5.00 EUR
- Stage 3: 10.00 EUR

### Filtering Rules

- Minimum amount: 1.00 EUR
- Stop list patterns (regex)
- Maximum stage: 3
- Recent dunning: 1 day minimum between notices

## API Integration

### Read-API Client

```python
# Get overdue invoices
response = read_client.get_overdue_invoices(
    pagination=CursorPagination(limit=100),
    correlation_id="CORR-001"
)

# Get invoice details
invoice = read_client.get_invoice_details(
    invoice_id="INV-001",
    correlation_id="CORR-001"
)
```

### Outbox Client

```python
# Publish dunning event
success = outbox_client.publish_dunning_issued(
    event=dunning_event,
    correlation_id="CORR-001"
)

# Check for duplicates
is_duplicate = outbox_client.check_duplicate_event(
    tenant_id="<UUID>",
    invoice_id="INV-001",
    stage=DunningStage.STAGE_1
)
```

## Flock Integration

### Playbook Creation

```python
playbook = DunningPlaybook(config)
flow = playbook.create_flow(context)
```

### Workflow Tasks

1. **scan_overdue_invoices**: Query overdue invoices
2. **compose_dunning_notices**: Generate notices from templates
3. **dispatch_dunning_events**: Publish events to outbox

### Context Management

```python
context = DunningContext(
    tenant_id="<UUID>",
    correlation_id="CORR-001",
    dry_run=False,
    limit=100
)
```

## Template System

### Jinja2 Templates

- `dunning_stage_1.jinja.txt`: Stage 1 notice template
- `dunning_stage_2.jinja.txt`: Stage 2 notice template
- `dunning_stage_3.jinja.txt`: Stage 3 notice template

### Template Variables

```python
{
    "notice": {
        "invoice_id": "INV-001",
        "amount_decimal": Decimal("150.00"),
        "dunning_fee_decimal": Decimal("2.50"),
        "total_amount_decimal": Decimal("152.50"),
        "due_date": datetime(...),
        "recipient_email": "customer@example.com",
        "recipient_name": "Customer Name"
    },
    "config": {
        "company_name": "0Admin",
        "support_email": "support@0admin.com",
        "company_address": "Address"
    }
}
```

## Event Schemas

### DUNNING_ISSUED Event

```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "invoice_id": "string",
  "stage": 1,
  "channel": "email",
  "notice_ref": "string",
  "due_date": "2024-01-15T00:00:00Z",
  "amount": "150.00",
  "correlation_id": "uuid"
}
```

### DUNNING_ESCALATED Event

```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "invoice_id": "string",
  "from_stage": 1,
  "to_stage": 2,
  "channel": "email",
  "notice_ref": "string",
  "due_date": "2024-01-15T00:00:00Z",
  "amount": "150.00",
  "reason": "Payment deadline exceeded",
  "escalated_at": "2024-01-25T10:30:00Z",
  "correlation_id": "uuid"
}
```

### DUNNING_RESOLVED Event

```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "invoice_id": "string",
  "stage": 2,
  "resolution": "payment_received",
  "resolved_at": "2024-01-30T14:45:00Z",
  "correlation_id": "uuid",
  "resolution_details": "Full payment received",
  "amount_paid": "155.00",
  "payment_reference": "TXN-001"
}
```

## Usage Examples

### Command Line

```bash
# Dry run for tenant
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --dry-run \
  --limit 25

# Production run
python tools/flock/playbook_mahnwesen.py \
  --tenant 00000000-0000-0000-0000-000000000001 \
  --limit 100 \
  --correlation-id CORR-001
```

### Programmatic Usage

```python
from agents.mahnwesen import DunningConfig, DunningPlaybook
from agents.mahnwesen.playbooks import DunningContext

# Create configuration
config = DunningConfig.from_tenant("00000000-0000-0000-0000-000000000001")

# Create context
context = DunningContext(
    tenant_id="00000000-0000-0000-0000-000000000001",
    correlation_id="CORR-001",
    dry_run=False,
    limit=100
)

# Run dunning process
playbook = DunningPlaybook(config)
result = playbook.run_once(context)

print(f"Notices created: {result.notices_created}")
print(f"Events dispatched: {result.events_dispatched}")
print(f"Processing time: {result.processing_time_seconds}s")
```

## Testing

### Offline Tests

```bash
# Run offline tests
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q \
  tests/agents_mahnwesen/test_overdue_rules_offline.py \
  tests/agents_mahnwesen/test_compose_template_offline.py \
  tests/agents_mahnwesen/test_dispatch_event_offline.py \
  tests/agents_mahnwesen/test_flock_integration_offline.py
```

### Database Tests

```bash
# Run database tests (optional)
RUN_DB_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -q \
  tests/agents_mahnwesen/test_flow_smoke_localdb.py
```

## Security & Compliance

### PII Redaction

- IBAN masking in logs
- Email address masking
- Amount masking in debug logs
- Chunk log size limit: 200 bytes

### Rate Limiting

- Maximum 200 notices per hour per tenant
- Exponential backoff on 429/5xx responses
- In-memory rate limiting for offline tests

### Idempotency

- SHA-256 based idempotency keys
- Canonical key normalization (NFKC, CRLF→LF, Trim)
- Duplicate event detection
- Deterministic hash generation

## Monitoring & Observability

### Metrics

- `dunning_notices_created_total`
- `dunning_events_dispatched_total`
- `dunning_processing_duration_seconds`
- `dunning_errors_total`

### Logging

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO",
  "message": "Dunning process completed",
  "tenant_id": "00000000-0000-0000-0000-000000000001",
  "correlation_id": "CORR-001",
  "notices_created": 5,
  "events_dispatched": 5,
  "processing_time": 2.5
}
```

### Health Checks

- Read-API health: `/healthz`
- Outbox health: Database connectivity
- Flock health: Service availability

## Troubleshooting

### Common Issues

1. **Template rendering failures**: Check template syntax and variable availability
2. **API timeouts**: Increase `read_api_timeout` configuration
3. **Duplicate events**: Check idempotency key generation
4. **Rate limiting**: Monitor `max_notices_per_hour` setting

### Debug Mode

```bash
# Enable verbose logging
python tools/flock/playbook_mahnwesen.py \
  --tenant <UUID> \
  --verbose \
  --dry-run
```

### Replay & DLQ

- DLQ events can be replayed manually
- Replay requires admin approval
- Document resolution reason
- Update correlation ID for traceability

## Development

### Adding New Templates

1. Create template file in `agents/mahnwesen/templates/`
2. Update `TemplateEngine._load_templates()`
3. Add template tests
4. Update documentation

### Adding New Event Types

1. Define event schema in `docs/standards/event_schemas/`
2. Add event type to `DunningEvent` class
3. Implement publishing logic in `OutboxClient`
4. Add integration tests
5. Update documentation

### Configuration Changes

1. Add new config field to `DunningConfig`
2. Add environment variable support
3. Update tenant-specific overrides
4. Add configuration tests
5. Update documentation
