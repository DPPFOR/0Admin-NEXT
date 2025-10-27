import os
import uuid

from backend.core.config import settings


class StorageError(Exception):
    pass


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _join_uri(base_uri: str, *parts: str) -> str:
    if base_uri.startswith("file://"):
        base_path = base_uri[len("file://") :]
        abs_path = os.path.join(base_path, *parts)
        return f"file://{abs_path}"
    elif base_uri.startswith("sb://"):
        joined = "/".join([p.strip("/") for p in (base_uri, *parts)])
        return joined
    else:
        raise StorageError("Unsupported STORAGE_BASE_URI scheme")


def put_bytes(tenant_id: str, content_hash: str, data: bytes, file_ext: str) -> str:
    """Persist bytes to storage and return the URI.

    File backend layout: {BASE}/{tenant}/{hh}/{hash}{ext}
    """
    backend = settings.STORAGE_BACKEND
    base_uri = settings.STORAGE_BASE_URI

    if backend == "file":
        if not base_uri.startswith("file://"):
            raise StorageError("STORAGE_BASE_URI must be file:///... for file backend")

        base_path = base_uri[len("file://") :]
        hh = content_hash[:2]
        rel_path = os.path.join(tenant_id, hh)
        dir_path = os.path.join(base_path, rel_path)
        _ensure_dir(dir_path)
        filename = f"{content_hash}{file_ext}"
        abs_path = os.path.join(dir_path, filename)

        # Atomic write: temp → fsync → move
        if not os.path.exists(abs_path):
            _ensure_dir(os.path.dirname(abs_path))
            tmp_name = f".{content_hash}.{uuid.uuid4().hex}.tmp"
            tmp_path = os.path.join(dir_path, tmp_name)
            with open(tmp_path, "wb") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, abs_path)

        return f"file://{abs_path}"

    elif backend == "sb":
        # Explicitly not supported in v1
        raise StorageError("STORAGE_BACKEND=sb is not supported in v1 (file-only)")

    else:
        raise StorageError("Unsupported STORAGE_BACKEND; expected 'file' or 'sb'")
