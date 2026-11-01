"""Tests for the Reelcard command-line interface."""

from __future__ import annotations

import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from reelcard.cli import build_parser, main
from reelcard.metadata import MetadataLookupError, MovieMetadata
from reelcard.poster import DEFAULT_HEIGHT, DEFAULT_WIDTH, PAPER, WHITE
from reelcard.video import VideoMetadata


def test_cli_help_lists_supported_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])

    assert exit_info.value.code == 0
    help_text = capsys.readouterr().out
    for option in (
        "--title",
        "--series",
        "--palette",
        "--include-black",
        "--year",
        "--director",
        "--writer",
        "--starring",
        "--runtime",
        "--rating",
        "--imdb-rating",
        "--plot",
        "--subtitle",
        "--credits",
        "--background-color",
        "--imdb-id",
        "--output",
        "--format",
        "--stripes",
        "--color-style",
        "--size",
        "--width",
        "--height",
        "--dpi",
        "--force",
    ):
        assert option in help_text


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["movie.mp4", "--year", "0"], "year must be between"),
        (["movie.mp4", "--stripes", "0"], "positive integer"),
        (["movie.mp4", "--dpi", "nan"], "positive finite number"),
    ],
)
def test_cli_rejects_invalid_argument_values(
    arguments: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(arguments)

    assert exit_info.value.code == 2
    assert message in capsys.readouterr().err


def test_cli_rejects_invalid_background_color(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["movie.mp4", "--background-color", "ultraviolet"])

    assert exit_info.value.code == 2
    assert "paper', 'white', or a six-digit hex color" in capsys.readouterr().err


@pytest.mark.parametrize(("value", "expected"), [("paper", PAPER), ("white", WHITE)])
def test_cli_parses_background_color_presets(
    value: str,
    expected: tuple[int, int, int],
) -> None:
    args = build_parser().parse_args(["movie.mp4", "--background-color", value])

    assert args.background_color == expected


def test_cli_defaults_to_white_background() -> None:
    args = build_parser().parse_args(["movie.mp4"])

    assert args.background_color == WHITE


def test_cli_requires_both_custom_dimensions_before_processing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "film.mp4"
    input_path.touch()
    with patch("reelcard.cli.probe_video") as probe:
        result = main([str(input_path), "--width", "620"])

    assert result == 2
    assert "--width and --height" in capsys.readouterr().err
    probe.assert_not_called()


def test_cli_rejects_portrait_dimensions_before_processing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "film.mp4"
    input_path.touch()
    with patch("reelcard.cli.probe_video") as probe:
        result = main(
            [str(input_path), "--width", "620", "--height", "874"]
        )

    assert result == 2
    assert "landscape" in capsys.readouterr().err
    probe.assert_not_called()


def test_cli_checks_missing_input_before_running_ffprobe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with patch("reelcard.cli.probe_video") as probe:
        result = main([str(tmp_path / "missing.mp4")])

    assert result == 2
    assert "does not exist" in capsys.readouterr().err
    probe.assert_not_called()


def test_cli_rejects_existing_output_without_force_before_processing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "film.mp4"
    output_path = tmp_path / "poster.png"
    input_path.touch()
    output_path.write_bytes(b"existing")

    with patch("reelcard.cli.probe_video") as probe:
        result = main([str(input_path), "--output", str(output_path)])

    assert result == 2
    assert "use --force" in capsys.readouterr().err
    assert output_path.read_bytes() == b"existing"
    probe.assert_not_called()


def test_cli_runs_pipeline_with_metadata_and_custom_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "custom.png"
    input_path.touch()
    monkeypatch.chdir(tmp_path)
    metadata = VideoMetadata(90.0, 1920, 1080, 0)
    barcode = Image.new("RGB", (3, 64), "red")
    poster = Image.new("RGB", (620, 874), "white")

    with (
        patch("reelcard.cli.probe_video", return_value=metadata) as probe,
        patch("reelcard.cli.iter_video_frames", return_value=iter(())) as frames,
        patch("reelcard.cli.make_barcode", return_value=barcode) as make_barcode,
        patch("reelcard.cli.render_poster", return_value=poster) as render,
        patch("reelcard.cli.save_poster") as save,
    ):
        result = main(
            [
                str(input_path),
                "--title",
                "Film Title",
                "--year",
                "1994",
                "--director",
                "Director",
                "--writer",
                "Writer",
                "--starring",
                "Lead Cast",
                "--runtime",
                "  122   min ",
                "--rating",
                "R",
                "--imdb-rating",
                "8.0/10",
                "--plot",
                "A plot summary",
                "--subtitle",
                "Subtitle",
                "--credits",
                "Credits",
                "--output",
                str(output_path),
                "--stripes",
                "3",
                "--color-style",
                "vivid",
                "--imdb-id",
                "tt0000001",
                "--width",
                "874",
                "--height",
                "620",
                "--dpi",
                "150",
                "--background-color",
                "#e8dfc8",
                "--force",
            ]
        )

    assert result == 0
    probe.assert_called_once_with(input_path)
    frames.assert_called_once_with(input_path, 3, metadata=metadata)
    make_barcode.assert_called_once()
    assert make_barcode.call_args.kwargs["color_style"] == "vivid"
    render.assert_called_once_with(
        barcode,
        title="Film Title",
        runtime_seconds=90.0,
        year=1994,
        director="Director",
        writer="Writer",
        starring="Lead Cast",
        runtime="122 min",
        rating="R",
        imdb_rating="8.0/10",
        plot="A plot summary",
        subtitle="Subtitle",
        credits="Credits",
        background_color=(232, 223, 200),
        width=874,
        height=620,
        dpi=150.0,
    )
    save.assert_called_once_with(poster, output_path, dpi=150.0, overwrite=True)
    assert f"Saved poster to {output_path}" in capsys.readouterr().out


def test_cli_default_output_uses_sanitized_title_and_preset_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "My Film.mp4"
    input_path.touch()
    monkeypatch.chdir(tmp_path)
    metadata = VideoMetadata(60.0, 640, 480, 0)

    with (
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=Image.new("RGB", (1, 64))) as make_barcode,
        patch("reelcard.cli.render_poster") as render,
        patch("reelcard.cli.save_poster") as save,
    ):
        assert main([str(input_path)]) == 0

    assert make_barcode.call_args.kwargs["color_style"] == "natural"
    render.assert_called_once()
    assert render.call_args.kwargs["width"] == DEFAULT_WIDTH
    assert render.call_args.kwargs["height"] == DEFAULT_HEIGHT
    assert save.call_args.args[1] == tmp_path / "My-Film.png"


def test_cli_palette_mode_uses_palette_swatches_in_poster_layout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "Film.mp4"
    input_path.touch()
    monkeypatch.chdir(tmp_path)
    metadata = VideoMetadata(60.0, 640, 480, 0)
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255)]
    barcode = Image.new("RGB", (3, 64))
    with (
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_palette", return_value=palette) as make_palette,
        patch("reelcard.cli.render_palette", return_value=barcode) as render,
        patch(
            "reelcard.cli.render_poster",
            return_value=Image.new("RGB", (620, 400)),
        ) as render_poster,
        patch("reelcard.cli.save_poster") as save,
    ):
        assert main(
            [
                str(input_path),
                "--palette",
                "--include-black",
                "--width",
                "620",
                "--height",
                "400",
            ]
        ) == 0

    assert make_palette.call_args.kwargs["include_black"] is True
    render.assert_called_once_with(palette, width=3, height=64)
    render_poster.assert_called_once()
    assert render_poster.call_args.args[0] is barcode
    assert render_poster.call_args.kwargs["title"] == "Film"
    assert render_poster.call_args.kwargs["width"] == 620
    assert render_poster.call_args.kwargs["height"] == 400
    save.assert_called_once()
    assert save.call_args.args[1] == tmp_path / "Film-palette.png"


def test_cli_palette_svg_mode_uses_normal_vector_poster_layout(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "Film.mp4"
    output_path = tmp_path / "palette.svg"
    input_path.touch()
    metadata = VideoMetadata(60.0, 640, 480, 0)
    palette = [(255, 0, 0), (0, 255, 0)]
    barcode = Image.new("RGB", (2, 64))
    with (
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_palette", return_value=palette),
        patch("reelcard.cli.render_palette", return_value=barcode),
        patch("reelcard.cli.render_svg", return_value="<svg poster/>") as render,
        patch("reelcard.cli.save_svg") as save,
    ):
        assert main(
            [
                str(input_path),
                "--palette",
                "--format",
                "svg",
                "--output",
                str(output_path),
                "--width",
                "620",
                "--height",
                "400",
            ]
        ) == 0

    render.assert_called_once()
    assert render.call_args.args[0] is barcode
    assert render.call_args.kwargs["title"] == "Film"
    assert render.call_args.kwargs["width"] == 620
    assert render.call_args.kwargs["height"] == 400
    save.assert_called_once_with("<svg poster/>", output_path, overwrite=False)


def test_cli_palette_mode_includes_imdb_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "Film.mp4"
    input_path.touch()
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    metadata = VideoMetadata(60.0, 640, 480, 0)
    movie_metadata = MovieMetadata(
        title="Matched Film",
        year=1994,
        director="A Director",
        imdb_rating="8.0/10",
        plot="A plot",
    )
    with (
        patch("reelcard.cli.lookup_movie", return_value=movie_metadata) as lookup,
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_palette", return_value=[(20, 40, 60)]),
        patch("reelcard.cli.render_palette", return_value=Image.new("RGB", (1, 64))),
        patch("reelcard.cli.render_poster") as render,
        patch("reelcard.cli.save_poster"),
    ):
        assert main([str(input_path), "--palette", "--imdb-id", "tt0000001"]) == 0

    lookup.assert_called_once_with(imdb_id="tt0000001", api_key="test-key")
    assert render.call_args.kwargs["title"] == "Matched Film"
    assert render.call_args.kwargs["year"] == 1994
    assert render.call_args.kwargs["director"] == "A Director"
    assert render.call_args.kwargs["imdb_rating"] == "8.0/10"
    assert render.call_args.kwargs["plot"] == "A plot"


def test_cli_requires_palette_mode_for_include_black(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "Film.mp4"
    input_path.touch()

    result = main([str(input_path), "--include-black"])

    assert result == 2
    assert "--include-black requires --palette" in capsys.readouterr().err


def test_cli_rejects_palette_mode_for_series(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.touch()
    second.touch()
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":[{"path":"first.mp4","year":1980},'
        '{"path":"second.mp4","year":1990}]}',
        encoding="utf-8",
    )

    result = main(["--series", str(manifest), "--palette"])

    assert result == 2
    assert "--palette cannot be combined with --series" in capsys.readouterr().err


def test_cli_renders_series_oldest_first_as_one_stacked_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    older = tmp_path / "older.mp4"
    newer = tmp_path / "newer.mp4"
    older.touch()
    newer.touch()
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":['
        '{"path":"newer.mp4","title":"Newer","year":2000},'
        '{"path":"older.mp4","title":"Older","year":1980}]}',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    metadata = VideoMetadata(60.0, 640, 480, 0)
    rendered: list[str] = []
    backgrounds: list[tuple[int, int, int]] = []

    def render_panel(_barcode, *, title, **kwargs):
        rendered.append(title)
        backgrounds.append(kwargs["background_color"])
        color = "blue" if title == "Newer" else "red"
        return Image.new("RGB", (kwargs["width"], kwargs["height"]), color)

    with (
        patch("reelcard.cli.probe_video", return_value=metadata) as probe,
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=Image.new("RGB", (1, 1))),
        patch("reelcard.cli.render_poster", side_effect=render_panel),
        patch("reelcard.cli.save_poster") as save,
    ):
        result = main(
            [
                "--series",
                str(manifest),
                "--width",
                "620",
                "--height",
                "400",
                "--background-color",
                "white",
            ]
        )

    assert result == 0
    assert [call.args[0] for call in probe.call_args_list] == [older, newer]
    assert rendered == ["Older", "Newer"]
    assert backgrounds == [WHITE, WHITE]
    combined = save.call_args.args[0]
    assert combined.size == (620, 800)
    assert combined.getpixel((0, 0)) == (255, 0, 0)
    assert combined.getpixel((0, 400)) == (0, 0, 255)
    assert save.call_args.args[1] == tmp_path / "series.png"
    assert "Saved series poster" in capsys.readouterr().out


def test_cli_series_svg_contains_one_vector_panel_per_movie(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.touch()
    second.touch()
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":[{"path":"first.mp4","year":1980},'
        '{"path":"second.mp4","year":1990}]}',
        encoding="utf-8",
    )
    metadata = VideoMetadata(60.0, 640, 480, 0)
    panel_svg = '<svg xmlns="http://www.w3.org/2000/svg"><rect width="10"/></svg>'

    with (
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=Image.new("RGB", (1, 1))),
        patch("reelcard.cli.render_svg", return_value=panel_svg),
        patch("reelcard.cli.save_svg") as save,
    ):
        assert main(
            [
                "--series",
                str(manifest),
                "--format",
                "svg",
                "--width",
                "620",
                "--height",
                "400",
            ]
        ) == 0

    root = ET.fromstring(save.call_args.args[0])
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    panels = root.findall("./svg:svg", namespace)
    assert len(panels) == 2
    assert [panel.attrib["y"] for panel in panels] == ["0", "400"]


def test_cli_series_uses_imdb_metadata_and_sorts_by_lookup_year(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    older = tmp_path / "older.mp4"
    newer = tmp_path / "newer.mp4"
    older.touch()
    newer.touch()
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":['
        '{"path":"newer.mp4","imdb_id":"tt0000002","director":"Manual Director"},'
        '{"path":"older.mp4","imdb_id":"tt0000001"}]}',
        encoding="utf-8",
    )
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    metadata = VideoMetadata(60.0, 640, 480, 0)
    rendered = []

    def render_panel(_barcode, **kwargs):
        rendered.append(kwargs)
        return Image.new("RGB", (kwargs["width"], kwargs["height"]))

    with (
        patch(
            "reelcard.cli.lookup_movie",
            side_effect=[
                MovieMetadata(title="Newer Movie", year=2000, director="Lookup Director"),
                MovieMetadata(title="Older Movie", year=1980, director="Older Director"),
            ],
        ) as lookup,
        patch("reelcard.cli.probe_video", return_value=metadata) as probe,
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=Image.new("RGB", (1, 1))),
        patch("reelcard.cli.render_poster", side_effect=render_panel),
        patch("reelcard.cli.save_poster"),
    ):
        assert main(
            [
                "--series",
                str(manifest),
                "--width",
                "620",
                "--height",
                "400",
            ]
        ) == 0

    assert [call.kwargs for call in lookup.call_args_list] == [
        {"imdb_id": "tt0000002", "api_key": "test-key"},
        {"imdb_id": "tt0000001", "api_key": "test-key"},
    ]
    assert [call.args[0] for call in probe.call_args_list] == [older, newer]
    assert [panel["title"] for panel in rendered] == ["Older Movie", "Newer Movie"]
    assert [panel["year"] for panel in rendered] == [1980, 2000]
    assert [panel["director"] for panel in rendered] == [
        "Older Director",
        "Manual Director",
    ]


def test_cli_series_requires_year_when_imdb_lookup_cannot_supply_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = tmp_path / "first.mp4"
    second = tmp_path / "second.mp4"
    first.touch()
    second.touch()
    manifest = tmp_path / "series.json"
    manifest.write_text(
        '{"movies":[{"path":"first.mp4","imdb_id":"tt0000001"},'
        '{"path":"second.mp4","year":2000}]}',
        encoding="utf-8",
    )

    with (
        patch("reelcard.cli.lookup_movie", side_effect=MetadataLookupError("lookup failed")),
        patch("reelcard.cli.probe_video") as probe,
    ):
        result = main(["--series", str(manifest)])

    assert result == 2
    assert "could not determine the release year" in capsys.readouterr().err
    probe.assert_not_called()


def test_cli_svg_format_uses_svg_output_and_default_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "Film.mp4"
    input_path.touch()
    monkeypatch.chdir(tmp_path)
    metadata = VideoMetadata(60.0, 640, 480, 0)
    barcode = Image.new("RGB", (1, 64), "red")

    with (
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=barcode),
        patch("reelcard.cli.render_poster") as render_png,
        patch("reelcard.cli.render_svg", return_value="<svg rendered/>") as render_svg,
        patch("reelcard.cli.save_svg") as save_svg,
    ):
        assert main([str(input_path), "--format", "svg"]) == 0

    render_png.assert_not_called()
    render_svg.assert_called_once()
    save_svg.assert_called_once_with(
        "<svg rendered/>",
        tmp_path / "Film.svg",
        overwrite=False,
    )


def test_cli_lookup_fills_only_missing_manual_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "film.mp4"
    input_path.touch()
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    metadata = VideoMetadata(60.0, 640, 480, 0)
    barcode = Image.new("RGB", (1, 64), "red")
    with (
        patch(
            "reelcard.cli.lookup_movie",
            return_value=MovieMetadata(
                title="Matched Film",
                year=1984,
                director="Lookup Director",
                writer="Lookup Writer",
                starring="Lookup Actor",
                runtime="122 min",
                rating="R",
                imdb_rating="8.0/10",
                plot="A lookup plot",
            ),
        ) as find,
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=barcode),
        patch("reelcard.cli.render_poster") as render,
        patch("reelcard.cli.save_poster"),
    ):
        assert main(
            [
                str(input_path),
                "--imdb-id",
                "tt0000001",
                "--title",
                "Manual Film",
                "--year",
                "1999",
                "--director",
                "Manual Director",
                "--runtime",
                "125 min",
                "--imdb-rating",
                "7.9/10",
            ]
        ) == 0

    find.assert_called_once()
    assert find.call_args.kwargs["imdb_id"] == "tt0000001"
    assert find.call_args.kwargs["api_key"] == "test-key"
    assert render.call_args.kwargs["title"] == "Manual Film"
    assert render.call_args.kwargs["year"] == 1999
    assert render.call_args.kwargs["director"] == "Manual Director"
    assert render.call_args.kwargs["writer"] == "Lookup Writer"
    assert render.call_args.kwargs["starring"] == "Lookup Actor"
    assert render.call_args.kwargs["runtime"] == "125 min"
    assert render.call_args.kwargs["rating"] == "R"
    assert render.call_args.kwargs["imdb_rating"] == "7.9/10"
    assert render.call_args.kwargs["plot"] == "A lookup plot"


def test_cli_uses_omdb_runtime_when_manual_runtime_is_not_given(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "film.mp4"
    input_path.touch()
    monkeypatch.setenv("OMDB_API_KEY", "test-key")
    metadata = VideoMetadata(60.0, 640, 480, 0)
    with (
        patch(
            "reelcard.cli.lookup_movie",
            return_value=MovieMetadata(runtime="122 min"),
        ),
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=Image.new("RGB", (1, 64))),
        patch("reelcard.cli.render_poster") as render,
        patch("reelcard.cli.save_poster"),
    ):
        assert main([str(input_path), "--imdb-id", "tt0000001"]) == 0

    assert render.call_args.kwargs["runtime"] == "122 min"


def test_cli_rejects_empty_manual_runtime(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "film.mp4"
    input_path.touch()

    with pytest.raises(SystemExit) as exit_info:
        main([str(input_path), "--runtime", "   "])

    assert exit_info.value.code == 2
    assert "runtime must not be empty" in capsys.readouterr().err


def test_cli_lookup_failure_warns_and_generates_poster(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "Film.mp4"
    input_path.touch()
    metadata = VideoMetadata(60.0, 640, 480, 0)
    barcode = Image.new("RGB", (1, 64), "red")

    with (
        patch(
            "reelcard.cli.lookup_movie",
            side_effect=MetadataLookupError("OMDB_API_KEY is missing"),
        ),
        patch("reelcard.cli.probe_video", return_value=metadata),
        patch("reelcard.cli.iter_video_frames", return_value=iter(())),
        patch("reelcard.cli.make_barcode", return_value=barcode),
        patch("reelcard.cli.render_poster") as render,
        patch("reelcard.cli.save_poster"),
    ):
        result = main([str(input_path), "--imdb-id", "tt0000001"])

    assert result == 0
    assert "Continuing without lookup" in capsys.readouterr().err
    render.assert_called_once()


def test_cli_svg_format_rejects_mismatched_output_extension(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "film.mp4"
    input_path.touch()

    result = main(
        [
            str(input_path),
            "--format",
            "svg",
            "--output",
            str(tmp_path / "film.png"),
        ]
    )

    assert result == 2
    assert ".svg extension" in capsys.readouterr().err


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg and FFprobe are required for the CLI integration test",
)
def test_cli_generates_poster_from_synthetic_video(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = tmp_path / "Synthetic Film.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=96x64:rate=2:duration=2",
            "-c:v",
            "ffv1",
            str(input_path),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    monkeypatch.chdir(tmp_path)

    result = main([str(input_path), "--stripes", "2"])
    output_path = tmp_path / "Synthetic-Film.png"

    assert result == 0
    assert output_path.is_file()
    with Image.open(output_path) as poster:
        assert poster.format == "PNG"
        assert poster.size == (DEFAULT_WIDTH, DEFAULT_HEIGHT)
        assert poster.info["dpi"] == pytest.approx((300, 300), abs=0.1)
