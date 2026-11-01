"""Movie-series manifest loading and validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MOVIE_FIELDS = {
    "path",
    "title",
    "year",
    "imdb_id",
    "director",
    "writer",
    "starring",
    "runtime",
    "rating",
    "imdb_rating",
    "plot",
    "subtitle",
    "credits",
}


@dataclass(frozen=True)
class SeriesMovie:
    """A movie and its poster metadata from a series manifest."""

    path: Path
    title: str | None = None
    year: int | None = None
    imdb_id: str | None = None
    director: str | None = None
    writer: str | None = None
    starring: str | None = None
    runtime: str | None = None
    rating: str | None = None
    imdb_rating: str | None = None
    plot: str | None = None
    subtitle: str | None = None
    credits: str | None = None


def load_series_manifest(path: str | Path) -> list[SeriesMovie]:
    """Load a JSON manifest and sort movies by year, preserving ties."""
    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"could not read series manifest {manifest_path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ValueError(f"series manifest is not valid UTF-8: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"series manifest is not valid JSON at line {exc.lineno}, "
            f"column {exc.colno}"
        ) from exc

    if not isinstance(data, dict) or set(data) != {"movies"}:
        raise ValueError("series manifest must be an object containing only a 'movies' list")
    entries = data["movies"]
    if not isinstance(entries, list) or len(entries) < 2:
        raise ValueError("series manifest must contain at least two movies")

    movies = [
        _parse_movie(entry, index, manifest_path.parent)
        for index, entry in enumerate(entries, start=1)
    ]
    return movies


def _parse_movie(entry: Any, index: int, base_path: Path) -> SeriesMovie:
    if not isinstance(entry, dict):
        raise ValueError(f"movie {index} in series manifest must be an object")
    unknown_fields = set(entry) - _MOVIE_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise ValueError(f"movie {index} has unknown field(s): {fields}")

    raw_path = entry.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"movie {index} must have a non-empty 'path'")
    movie_path = Path(raw_path)
    if not movie_path.is_absolute():
        movie_path = base_path / movie_path

    year = entry.get("year")
    if year is not None and (
        isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9999
    ):
        raise ValueError(
            f"movie {index} field 'year' must be an integer from 1 to 9999"
        )
    imdb_id = _optional_text(entry, "imdb_id", index)
    if year is None and imdb_id is None:
        raise ValueError(
            f"movie {index} must have a release 'year' or an 'imdb_id' "
            "that can provide its year"
        )
    optional_fields = {
        field: _optional_text(entry, field, index)
        for field in _MOVIE_FIELDS - {"path", "title", "year", "imdb_id"}
    }
    return SeriesMovie(
        path=movie_path,
        title=_optional_text(entry, "title", index),
        year=year,
        imdb_id=imdb_id,
        director=optional_fields["director"],
        writer=optional_fields["writer"],
        starring=optional_fields["starring"],
        runtime=optional_fields["runtime"],
        rating=optional_fields["rating"],
        imdb_rating=optional_fields["imdb_rating"],
        plot=optional_fields["plot"],
        subtitle=optional_fields["subtitle"],
        credits=optional_fields["credits"],
    )


def _optional_text(entry: dict[str, Any], field: str, index: int) -> str | None:
    value = entry.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"movie {index} field {field!r} must be a non-empty string when provided"
        )
    return " ".join(value.split())
