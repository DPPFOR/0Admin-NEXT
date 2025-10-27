"""Core configuration with Pydantic v2 Settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    app_env: str = "development"
    database_url: str = "postgresql://user:password@localhost/dbname"
    log_level: str = "INFO"
    enable_metrics: bool = True

    # Upload API configuration
    # Max upload size in MB (default 25)
    MAX_UPLOAD_MB: int = 25
    # CSV string of allowed MIME types
    MIME_ALLOWLIST: str = (
        "application/pdf,"
        "image/png,"
        "image/jpeg,"
        "text/csv,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,"
        "application/json,"
        "application/xml"
    )
    # Storage backend: 'file' or 'sb'
    STORAGE_BACKEND: str = "file"
    # Base URI for storage; e.g. file:///var/0admin/uploads or sb://bucket/prefix
    STORAGE_BASE_URI: str = "file:///var/0admin/uploads"

    # Auth: optional service-token whitelist (CSV). If non-empty, tokens must be in this list.
    AUTH_SERVICE_TOKENS: str = ""

    # Programmatic ingest settings
    INGEST_TIMEOUT_CONNECT_MS: int = 2000
    INGEST_TIMEOUT_READ_MS: int = 5000
    INGEST_REDIRECT_LIMIT: int = 3
    INGEST_URL_ALLOWLIST: str = (
        ""  # CSV of allowed domains/suffixes; if set, only these are allowed
    )
    INGEST_URL_DENYLIST: str = ""  # CSV of denied domains/suffixes

    # Worker / Parser settings
    WORKER_BATCH_SIZE: int = 50
    WORKER_POLL_INTERVAL_MS: int = 1000
    PARSER_MAX_BYTES: int = 10_000_000
    PARSER_CHUNK_THRESHOLD_BYTES: int = 262_144
    PARSER_RETRY_MAX: int = 3
    PARSER_BACKOFF_STEPS: str = "5,30,300"  # seconds

    # Mail ingest settings
    MAIL_PROVIDER: str = "imap"  # imap|graph
    MAILBOX_NAME: str = "INBOX"
    MAIL_BATCH_LIMIT: int = 50
    MAIL_SINCE_HOURS: int = 24
    MAIL_POLL_INTERVAL_MS: int = 0
    MAIL_MAX_BYTES_PER_RUN: int = 50_000_000
    MAIL_RETRY_MAX: int = 3
    MAIL_BACKOFF_STEPS: str = "1000,5000,10000"  # ms
    MAIL_CONNECTOR_AUTO: bool = False
    # IMAP
    IMAP_HOST: str = ""
    IMAP_PORT: int = 993
    IMAP_SSL: bool = True
    IMAP_USERNAME: str = ""
    IMAP_PASSWORD: str = ""
    # Graph
    GRAPH_TENANT_ID: str = ""
    GRAPH_CLIENT_ID: str = ""
    GRAPH_CLIENT_SECRET: str = ""
    GRAPH_USER_ID: str = ""

    # Read/Ops API settings
    READ_MAX_LIMIT: int = 100
    CURSOR_HMAC_KEY: str = "dev-secret-key-change"
    ADMIN_TOKENS: str = ""  # CSV; tokens with admin rights for ops endpoints

    # Outbox publisher settings
    PUBLISH_TRANSPORT: str = "stdout"  # stdout|webhook
    PUBLISH_BATCH_SIZE: int = 50
    PUBLISH_POLL_INTERVAL_MS: int = 1000
    PUBLISH_BACKOFF_STEPS: str = "5,30,300"
    PUBLISH_RETRY_MAX: int = 3
    # Webhook transport
    WEBHOOK_URL: str = ""
    WEBHOOK_TIMEOUT_MS: int = 3000
    WEBHOOK_SUCCESS_CODES: str = "200-299"
    WEBHOOK_HEADERS_ALLOWLIST: str = ""  # CSV of key=value to include
    WEBHOOK_DOMAIN_ALLOWLIST: str = ""  # CSV of allowed webhook domains (host suffixes)

    # Security / rotation
    TOKEN_ROTATION_WINDOW_DAYS: int = 90

    # MCP shadow analysis: optional info-event emission (local-only)
    MCP_SHADOW_EMIT_ANALYSIS_EVENT: bool = False


# Global settings instance
settings = Settings()
