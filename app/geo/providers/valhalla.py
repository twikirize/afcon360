# app/geo/providers/valhalla.py
"""
AFCON360 GEO - Valhalla routing adapter.

Valhalla is the primary road-routing engine behind the provider-neutral GEO
interface. All measurements crossing this boundary are normalized to metres
and seconds; unresolved measurements remain None.

Network I/O occurs only inside route() and matrix(). Provider construction,
is_available(), and health inspection are network-free. There are no retries.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import List, Tuple

import requests

from app.geo.interfaces import GeoPoint, RouteResult, RoutingProvider
from app.geo.providers.base import BaseProvider
from app.utils.exceptions import ValidationError
from app.utils.validators import TransportValidators

logger = logging.getLogger(__name__)


@dataclass
class ValhallaConfig:
    base_url: str = ""
    timeout_s: float = 10.0
    enabled: bool = False  # disabled until operator configures endpoint


def _decode_polyline(shape: str, precision: int = 6) -> List[Tuple[float, float]]:
    """Decode an encoded polyline to [(latitude, longitude), ...].

    Precision 6 is Valhalla's shape default. Raises ValueError on truncated
    input so callers can map it to an unresolved result.
    """
    factor = 10 ** precision
    points: List[Tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0
    size = len(shape)
    while index < size:
        for axis in ("lat", "lng"):
            shift = 0
            value = 0
            while True:
                if index >= size:
                    raise ValueError("Truncated polyline shape")
                byte = ord(shape[index]) - 63
                if byte < 0 or byte > 0x3F:
                    raise ValueError("Invalid polyline character")
                index += 1
                value |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
                if shift > 60:
                    raise ValueError("Invalid polyline coordinate")
            delta = ~(value >> 1) if (value & 1) else (value >> 1)
            if axis == "lat":
                lat += delta
            else:
                lng += delta
        points.append((lat / factor, lng / factor))
    return points


class ValhallaRouter(BaseProvider, RoutingProvider):
    """Valhalla adapter. Live only when explicitly enabled and configured."""

    name = "valhalla"

    def __init__(self, config: ValhallaConfig | None = None):
        self.config = config or ValhallaConfig()

    def is_available(self) -> bool:
        return bool(self.config.enabled and self.config.base_url)

    @staticmethod
    def _validate_point(point: GeoPoint, name: str) -> None:
        """Reject out-of-range/non-numeric coordinates before any I/O."""
        try:
            valid = TransportValidators.validate_coordinates(
                point.latitude, point.longitude)
        except Exception:
            valid = False
        if not valid:
            raise ValidationError(
                f"Invalid {name}: latitude must be within [-90, 90] and "
                f"longitude within [-180, 180], got "
                f"({point.latitude!r}, {point.longitude!r})",
                field=name,
            )

    @staticmethod
    def _unresolved() -> RouteResult:
        return RouteResult(provider="valhalla", resolved=False)

    @staticmethod
    def _nonnegative_number(value, field: str) -> float:
        if isinstance(value, bool) or value is None:
            raise ValueError(f"Invalid Valhalla {field}")
        number = float(value)
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"Invalid Valhalla {field}")
        return number

    @classmethod
    def _kilometres_to_metres(cls, value, field: str) -> float:
        metres = cls._nonnegative_number(value, field) * 1000.0
        if not math.isfinite(metres):
            raise ValueError(f"Invalid Valhalla {field}")
        return metres

    @staticmethod
    def _is_kilometres(units) -> bool:
        return isinstance(units, str) and units.strip().lower() in (
            "kilometers", "kilometres", "km")

    def _unresolved_matrix(self, rows: int, columns: int) -> List[List[RouteResult]]:
        return [[self._unresolved() for _ in range(columns)]
                for _ in range(rows)]

    def route(self, origin: GeoPoint, destination: GeoPoint,
              profile: str = "auto") -> RouteResult:
        self._validate_point(origin, "origin")
        self._validate_point(destination, "destination")
        if not self.is_available():
            return self._unresolved()

        payload = {
            "locations": [
                {"lat": origin.latitude, "lon": origin.longitude},
                {"lat": destination.latitude, "lon": destination.longitude},
            ],
            "costing": profile,
            "units": "kilometers",
        }
        try:
            url = self.config.base_url.rstrip("/") + "/route"
            response = requests.post(url, json=payload,
                                     timeout=self.config.timeout_s)
            response.raise_for_status()
            data = response.json()
            trip = data["trip"]
            if not isinstance(trip, dict) or trip.get("status", 0) not in (0, "0"):
                raise ValueError("Valhalla route did not succeed")
            summary = trip["summary"]
            units = trip.get("units", data.get("units"))
            if not self._is_kilometres(units):
                raise ValueError("Unexpected Valhalla route distance units")

            distance_m = self._kilometres_to_metres(
                summary["length"], "route distance")
            duration_s = self._nonnegative_number(
                summary["time"], "route duration")

            geometry: List[GeoPoint] = []
            legs = trip.get("legs")
            if not isinstance(legs, list):
                raise ValueError("Invalid Valhalla route legs")
            for leg in legs:
                if not isinstance(leg, dict):
                    raise ValueError("Invalid Valhalla route leg")
                shape = leg.get("shape")
                if not isinstance(shape, str) or not shape:
                    raise ValueError("Missing Valhalla route shape")
                for lat, lng in _decode_polyline(shape, precision=6):
                    point = GeoPoint(latitude=lat, longitude=lng)
                    self._validate_point(point, "route_geometry")
                    geometry.append(point)
            if not geometry:
                raise ValueError("Valhalla returned no route geometry")

            return RouteResult(distance_m=distance_m,
                               duration_s=duration_s,
                               geometry=geometry,
                               provider=self.name,
                               resolved=True)
        except Exception as exc:
            # Provider exception messages can contain request URLs. Do not
            # write them to logs; keep only the exception class.
            logger.warning("Valhalla route request unresolved (%s)",
                           type(exc).__name__)
            return self._unresolved()

    def matrix(self, origins: List[GeoPoint],
               destinations: List[GeoPoint]) -> List[List[RouteResult]]:
        rows = len(origins)
        columns = len(destinations)
        if not origins:
            raise ValidationError("At least one origin is required",
                                  field="origins")
        if not destinations:
            raise ValidationError("At least one destination is required",
                                  field="destinations")

        for index, point in enumerate(origins):
            self._validate_point(point, f"origins[{index}]")
        for index, point in enumerate(destinations):
            self._validate_point(point, f"destinations[{index}]")

        if not self.is_available():
            return self._unresolved_matrix(rows, columns)

        payload = {
            "sources": [
                {"lat": point.latitude, "lon": point.longitude}
                for point in origins
            ],
            "targets": [
                {"lat": point.latitude, "lon": point.longitude}
                for point in destinations
            ],
            "costing": "auto",
            "units": "kilometers",
            "verbose": False,
        }
        try:
            url = self.config.base_url.rstrip("/") + "/sources_to_targets"
            response = requests.post(url, json=payload,
                                     timeout=self.config.timeout_s)
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not self._is_kilometres(
                    data.get("units")):
                raise ValueError("Invalid Valhalla matrix response units")

            result = data["sources_to_targets"]
            if not isinstance(result, dict):
                raise ValueError("Invalid Valhalla matrix result")
            distances = result["distances"]
            durations = result["durations"]
            if (not isinstance(distances, list)
                    or not isinstance(durations, list)
                    or len(distances) != rows
                    or len(durations) != rows):
                raise ValueError("Invalid Valhalla matrix row count")

            matrix: List[List[RouteResult]] = []
            for row_index in range(rows):
                distance_row = distances[row_index]
                duration_row = durations[row_index]
                if (not isinstance(distance_row, list)
                        or not isinstance(duration_row, list)
                        or len(distance_row) != columns
                        or len(duration_row) != columns):
                    raise ValueError("Invalid Valhalla matrix column count")

                result_row: List[RouteResult] = []
                for column_index in range(columns):
                    distance_km = distance_row[column_index]
                    duration_s = duration_row[column_index]
                    # Valhalla uses null/null for an unreachable pair.
                    if distance_km is None and duration_s is None:
                        result_row.append(self._unresolved())
                        continue
                    if distance_km is None or duration_s is None:
                        raise ValueError("Incomplete Valhalla matrix cell")
                    distance_m = self._kilometres_to_metres(
                        distance_km, "matrix distance")
                    duration_s = self._nonnegative_number(
                        duration_s, "matrix duration")
                    result_row.append(RouteResult(
                        distance_m=distance_m,
                        duration_s=duration_s,
                        provider=self.name,
                        resolved=True,
                    ))
                matrix.append(result_row)
            return matrix
        except Exception as exc:
            logger.warning("Valhalla matrix request unresolved (%s)",
                           type(exc).__name__)
            return self._unresolved_matrix(rows, columns)
