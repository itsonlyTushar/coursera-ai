"""Read-only Qdrant access used to build collection metrics for the dashboard."""
from functools import lru_cache
import time
from typing import Any

from fastapi import HTTPException
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.schemas import CollectionResponse, MetricsResponse


logger = get_logger(__name__)

# The dashboard polls /api/metrics, and each call scans the collection. Cache
# the aggregated result briefly to avoid repeated full scans.
_METRICS_TTL_SECONDS = 30.0
_SCROLL_BATCH = 256


class QdrantService:
    def __init__(self, settings: Settings) -> None:
        # Builds a reusable Qdrant client from config so every request shares one connection.
        self.settings = settings
        self.client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.resolved_qdrant_api_key,
            timeout=60,
            check_compatibility=False,
        )
        self._metrics_cache: tuple[float, int, MetricsResponse] | None = None

    def metrics(self, scan_limit: int) -> MetricsResponse:
        # Returns collection counts/breakdowns, serving a short-lived cache so dashboard polling stays cheap.
        cached = self._metrics_cache
        if cached and cached[1] == scan_limit and (time.monotonic() - cached[0]) < _METRICS_TTL_SECONDS:
            return cached[2]

        collection = self._get_collection()
        records = self._scroll_payloads(scan_limit)
        result = MetricsResponse(
            collection_name=self.settings.qdrant_collection,
            qdrant_status=collection.status,
            points_count=collection.points_count,
            scanned_records=len(records),
            content_type_counts=_counts(records, "content_type"),
            course_id_counts=_counts(records, "course_id"),
            embedding_model_counts=_counts(records, "embedding_model"),
        )
        self._metrics_cache = (time.monotonic(), scan_limit, result)
        return result

    def _get_collection(self) -> CollectionResponse:
        # Fetches collection status/counts and normalizes Qdrant errors into clean HTTP 502s.
        try:
            collection = self.client.get_collection(self.settings.qdrant_collection)
        except UnexpectedResponse as exc:
            logger.error("Qdrant returned an error for get_collection: %s", exc)
            raise HTTPException(status_code=502, detail="Could not read the Qdrant collection.") from exc
        except Exception as exc:
            logger.error("Could not reach Qdrant: %s", exc)
            raise HTTPException(status_code=502, detail="Could not reach the vector store.") from exc

        return CollectionResponse(
            collection_name=self.settings.qdrant_collection,
            status=str(getattr(collection, "status", None)),
            vectors_count=getattr(collection, "vectors_count", None),
            points_count=getattr(collection, "points_count", None),
            indexed_vectors_count=getattr(collection, "indexed_vectors_count", None),
            config=_model_dump(getattr(collection, "config", None)),
        )

    def _scroll_payloads(self, scan_limit: int) -> list[dict[str, Any]]:
        # Pages through the collection up to scan_limit so metrics can aggregate payload fields.
        payloads: list[dict[str, Any]] = []
        offset: Any = None

        while len(payloads) < scan_limit:
            batch_limit = min(_SCROLL_BATCH, scan_limit - len(payloads))
            try:
                points, offset = self.client.scroll(
                    collection_name=self.settings.qdrant_collection,
                    limit=batch_limit,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as exc:
                logger.error("Could not scan Qdrant records: %s", exc)
                raise HTTPException(status_code=502, detail="Could not scan the vector store.") from exc

            if not points:
                break
            payloads.extend(point.payload or {} for point in points)
            if offset is None:
                break

        return payloads


def _iter_values(value: Any) -> list[str]:
    # Normalizes a payload field (scalar or list) into a list of non-empty strings so counting is uniform.
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item is not None and str(item).strip()]
    return [str(value)] if str(value).strip() else []


def _counts(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    # Tallies how often each value of a field appears, sorted by frequency, for the metrics breakdowns.
    counts: dict[str, int] = {}
    for record in records:
        for value in _iter_values(record.get(key)):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _model_dump(value: Any) -> dict[str, Any]:
    # Converts a Qdrant config object into a plain dict across client versions so it serializes cleanly.
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return {}


@lru_cache
def get_qdrant_service() -> QdrantService:
    # Provides a cached singleton service as a FastAPI dependency so the client is reused across requests.
    return QdrantService(get_settings())
