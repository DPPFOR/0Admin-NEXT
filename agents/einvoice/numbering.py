"""Nummernkreis-Service (A1) für EN16931-Rechnungen."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from heapq import heappop, heappush
from typing import Callable, Dict, List, Optional, Tuple


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


class NumberingError(RuntimeError):
    pass


class ReservationNotFoundError(NumberingError):
    pass


class ReservationStateError(NumberingError):
    pass


@dataclass
class Reservation:
    reservation_id: str
    tenant_id: str
    year: int
    sequence: int
    channel: Optional[str]
    created_at: datetime
    status: str = "reserved"
    invoice_no: Optional[str] = None
    idempotency_key: Optional[str] = None


class NumberingService:
    """Verwaltet Reservierungen und Nummernkreise pro Tenant und Jahr."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
        format_strategy: Callable[[str, int, int, Optional[str]], str] | None = None,
        format_name: str = "einvoice-default",
    ) -> None:
        self._clock = clock or _default_clock
        self._format_strategy = format_strategy or self._default_format
        self._format_name = format_name
        self._reservations: Dict[str, Reservation] = {}
        self._sequences: Dict[Tuple[str, int], int] = {}
        self._available: Dict[Tuple[str, int], List[int]] = {}
        self._reservation_counter = 0
        self.audit_log: List[Dict[str, object]] = []

    def reserve(self, tenant_id: str, invoice_date: date, channel: Optional[str] = None) -> str:
        if not tenant_id:
            raise ValueError("tenant_id is required")
        if not isinstance(invoice_date, date):
            raise ValueError("invoice_date must be a date")

        year = invoice_date.year
        sequence = self._next_sequence(tenant_id, year)
        reservation_id = self._generate_reservation_id()
        created_at = self._clock()

        reservation = Reservation(
            reservation_id=reservation_id,
            tenant_id=tenant_id,
            year=year,
            sequence=sequence,
            channel=channel,
            created_at=created_at,
        )
        self._reservations[reservation_id] = reservation
        self._log("reserve", reservation)
        return reservation_id

    def commit(self, reservation_id: str) -> str:
        reservation = self._get_reservation(reservation_id)
        if reservation.status == "aborted":
            raise ReservationStateError("cannot commit aborted reservation")

        if reservation.status == "committed":
            assert reservation.invoice_no is not None
            return reservation.invoice_no

        invoice_no = self._format_strategy(
            reservation.tenant_id,
            reservation.year,
            reservation.sequence,
            reservation.channel,
        )
        reservation.invoice_no = invoice_no
        reservation.status = "committed"
        reservation.idempotency_key = (
            f"{reservation.tenant_id}|{invoice_no}|{self._format_name}"
        )
        self._log("commit", reservation)
        return invoice_no

    def abort(self, reservation_id: str) -> None:
        reservation = self._get_reservation(reservation_id)
        if reservation.status == "committed":
            raise ReservationStateError("cannot abort committed reservation")
        if reservation.status == "aborted":
            raise ReservationStateError("reservation already aborted")

        reservation.status = "aborted"
        self._release_sequence(reservation)
        self._log("abort", reservation)

    def _generate_reservation_id(self) -> str:
        self._reservation_counter += 1
        return f"res-{self._reservation_counter:08d}"

    def _next_sequence(self, tenant_id: str, year: int) -> int:
        key = (tenant_id, year)
        available = self._available.setdefault(key, [])
        if available:
            return heappop(available)

        next_value = self._sequences.get(key, 0) + 1
        self._sequences[key] = next_value
        return next_value

    def _release_sequence(self, reservation: Reservation) -> None:
        key = (reservation.tenant_id, reservation.year)
        heappush(self._available.setdefault(key, []), reservation.sequence)

    def _get_reservation(self, reservation_id: str) -> Reservation:
        if reservation_id not in self._reservations:
            raise ReservationNotFoundError(f"Reservation {reservation_id} not found")
        return self._reservations[reservation_id]

    def _log(self, action: str, reservation: Reservation) -> None:
        self.audit_log.append(
            {
                "action": action,
                "reservation_id": reservation.reservation_id,
                "tenant_id": reservation.tenant_id,
                "year": reservation.year,
                "sequence": reservation.sequence,
                "status": reservation.status,
                "channel": reservation.channel,
                "invoice_no": reservation.invoice_no,
                "idempotency_key": reservation.idempotency_key,
                "timestamp": self._clock(),
            }
        )

    @staticmethod
    def _default_format(
        tenant_id: str,
        year: int,
        sequence: int,
        channel: Optional[str],
    ) -> str:
        channel_part = f"-{channel}" if channel else ""
        return f"INV{channel_part}-{year}-{sequence:05d}"

