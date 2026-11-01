"""Tests for movie-series manifest loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reelcard.series import load_series_manifest


def test_load_series_manifest_resolves_paths_and_preserves_manifest_order(
    tmp_path: Path,
) -> None:
    (tmp_path / "films").mkdir()
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":['
        '{"path":"films/late.mp4","title":"Late","year":2000},'
        '{"path":"films/first.mp4","year":1980},'
        '{"path":"films/tie.mp4","title":"Tie","year":1980}]}',
        encoding="utf-8",
    )

    movies = load_series_manifest(manifest)

    assert [movie.title for movie in movies] == ["Late", None, "Tie"]
    assert [movie.year for movie in movies] == [2000, 1980, 1980]
    assert [movie.path for movie in movies] == [
        tmp_path / "films" / "late.mp4",
        tmp_path / "films" / "first.mp4",
        tmp_path / "films" / "tie.mp4",
    ]


@pytest.mark.parametrize(
    ("movies", "message"),
    [
        ([{"path": "film.mp4", "year": None}, {"path": "other.mp4", "year": 2000}], "release 'year' or an 'imdb_id'"),
        ([{"path": "film.mp4"}, {"path": "other.mp4", "year": 2000}], "release 'year' or an 'imdb_id'"),
        ([{"path": "film.mp4", "year": 2000}], "at least two movies"),
        ([{"path": "film.mp4", "year": True}, {"path": "other.mp4", "year": 2000}], "integer from 1 to 9999"),
    ],
)
def test_load_series_manifest_rejects_missing_or_invalid_years(
    tmp_path: Path,
    movies: list[dict[str, object]],
    message: str,
) -> None:
    manifest = tmp_path / "series.json"
    manifest.write_text(json.dumps({"movies": movies}), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_series_manifest(manifest)


def test_load_series_manifest_rejects_unknown_fields(tmp_path: Path) -> None:
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":[{"path":"film.mp4","year":2000,"titel":"typo"},'
        '{"path":"other.mp4","year":2001}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unknown field"):
        load_series_manifest(manifest)


def test_load_series_manifest_reports_invalid_encoding(tmp_path: Path) -> None:
    manifest = tmp_path / "series.json"
    manifest.write_bytes(b"\xff")

    with pytest.raises(ValueError, match="valid UTF-8"):
        load_series_manifest(manifest)


def test_load_series_manifest_accepts_imdb_reference_without_year(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":[{"path":"film.mp4","imdb_id":"tt0000001"},'
        '{"path":"other.mp4","year":2001}]}',
        encoding="utf-8",
    )

    movies = load_series_manifest(manifest)

    assert movies[0].year is None
    assert movies[0].imdb_id == "tt0000001"
