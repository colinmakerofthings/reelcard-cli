"""Tests for representative colors and barcode rendering."""

from __future__ import annotations

import pytest
from PIL import Image

from reelcard.colors import (
    make_barcode,
    make_palette,
    render_palette,
    render_palette_svg,
    representative_color,
)
from reelcard.errors import FrameExtractionError
from reelcard.video import VideoFrame


def _frame(
    color: tuple[int, int, int],
    *,
    timestamp: float = 0.0,
    pixels: list[tuple[int, int, int]] | None = None,
) -> VideoFrame:
    pixel_values = pixels if pixels is not None else [color]
    rgb = bytes(channel for pixel in pixel_values for channel in pixel)
    return VideoFrame(timestamp, len(pixel_values), 1, rgb)


def test_representative_color_returns_uniform_frame_color() -> None:
    frame = _frame((27, 128, 241), pixels=[(27, 128, 241)] * 25)

    assert representative_color(frame) == (27, 128, 241)


def test_representative_color_trims_isolated_extreme_pixels() -> None:
    pixels = [(100, 120, 140)] * 98 + [(0, 0, 0), (255, 255, 255)]

    assert representative_color(_frame((0, 0, 0), pixels=pixels)) == (
        100,
        120,
        140,
    )


def test_representative_color_rounds_channel_means_to_nearest_integer() -> None:
    pixels = [(0, 10, 20), (1, 11, 21)]

    assert representative_color(_frame((0, 0, 0), pixels=pixels)) == (1, 11, 21)


@pytest.mark.parametrize(
    ("frame", "message"),
    [
        (VideoFrame(0.0, 0, 1, b""), "dimensions"),
        (VideoFrame(0.0, 2, 1, b"\x00\x00\x00"), "data length"),
    ],
)
def test_representative_color_rejects_invalid_frames(
    frame: VideoFrame,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        representative_color(frame)


@pytest.mark.parametrize("trim_fraction", [-0.1, 0.5, float("nan"), float("inf")])
def test_representative_color_rejects_invalid_trim_fraction(
    trim_fraction: float,
) -> None:
    with pytest.raises(ValueError, match="trim_fraction"):
        representative_color(_frame((1, 2, 3)), trim_fraction=trim_fraction)


def test_make_barcode_preserves_frame_order_in_vertical_stripes() -> None:
    frames = [
        _frame((255, 0, 0), timestamp=1.0),
        _frame((0, 255, 0), timestamp=2.0),
        _frame((0, 0, 255), timestamp=3.0),
    ]

    barcode = make_barcode(frames, height=4)

    assert barcode.size == (3, 4)
    assert list(barcode.getdata()) == [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
    ] * 4
    assert barcode.getpixel((0, 3)) == (255, 0, 0)
    assert barcode.getpixel((2, 0)) == (0, 0, 255)


def test_make_barcode_rejects_empty_frames() -> None:
    with pytest.raises(ValueError, match="at least one frame"):
        make_barcode([])


def test_make_barcode_rejects_out_of_order_frames() -> None:
    frames = [
        _frame((1, 2, 3), timestamp=2.0),
        _frame((4, 5, 6), timestamp=1.0),
    ]

    with pytest.raises(ValueError, match="chronological order"):
        make_barcode(frames)


def test_make_barcode_propagates_frame_extraction_failures() -> None:
    def failed_frames():
        yield _frame((1, 2, 3))
        raise FrameExtractionError("decode failed")

    with pytest.raises(FrameExtractionError, match="decode failed"):
        make_barcode(failed_frames())


@pytest.mark.parametrize("height", [0, -1, True, 1.5])
def test_make_barcode_rejects_invalid_height(height: int) -> None:
    with pytest.raises(ValueError, match="barcode height"):
        make_barcode([_frame((1, 2, 3))], height=height)


def test_make_barcode_is_deterministic() -> None:
    frames = [
        _frame((12, 34, 56), timestamp=1.0),
        _frame((78, 90, 123), timestamp=2.0),
    ]

    first = make_barcode(frames, height=8)
    second = make_barcode(frames, height=8)

    assert isinstance(first, Image.Image)
    assert first.tobytes() == second.tobytes()


def test_representative_color_keeps_bright_saturated_colors_over_shadows() -> None:
    pixels = [(0, 0, 0)] * 25 + [(210, 70, 25)] * 75

    color = representative_color(_frame((0, 0, 0), pixels=pixels))

    assert color == (210, 70, 25)


def test_make_barcode_does_not_apply_gamma_to_uniform_color() -> None:
    frame = _frame((32, 96, 200))

    assert make_barcode([frame]).getpixel((0, 0)) == (32, 96, 200)


def test_make_barcode_brighter_style_lifts_channels_moderately() -> None:
    barcode = make_barcode([_frame((80, 120, 160))], color_style="brighter")

    assert barcode.getpixel((0, 0)) == (92, 138, 184)


def test_make_barcode_vivid_style_increases_saturation() -> None:
    original = make_barcode([_frame((160, 100, 80))])
    vivid = make_barcode([_frame((160, 100, 80))], color_style="vivid")
    original_range = max(original.getpixel((0, 0))) - min(original.getpixel((0, 0)))
    vivid_range = max(vivid.getpixel((0, 0))) - min(vivid.getpixel((0, 0)))

    assert vivid_range > original_range


def test_make_barcode_rejects_unknown_color_style() -> None:
    with pytest.raises(ValueError, match="color_style"):
        make_barcode([_frame((1, 2, 3))], color_style="unknown")


def test_make_palette_finds_distinct_prominent_colors_and_ignores_black() -> None:
    colors = [(220, 20, 20)] * 8 + [(20, 30, 220)] * 5 + [(220, 210, 20)] * 2 + [(0, 0, 0)]
    frame = VideoFrame(
        1.0,
        4,
        4,
        bytes(channel for color in colors for channel in color),
    )

    palette = make_palette([frame])

    assert len(palette) == 3
    assert palette[0] == pytest.approx((220, 20, 20), abs=3)
    assert any(color == pytest.approx((20, 30, 220), abs=3) for color in palette)
    assert any(color == pytest.approx((220, 210, 20), abs=3) for color in palette)
    assert all(max(color) > 24 for color in palette)


def test_make_palette_can_include_black_and_returns_up_to_six_colors() -> None:
    colors = [(220, 20, 20)] * 8 + [(20, 30, 220)] * 5 + [(0, 0, 0)] * 3
    frame = VideoFrame(
        1.0,
        4,
        4,
        bytes(channel for color in colors for channel in color),
    )

    palette = make_palette([frame], include_black=True)

    assert len(palette) == 3
    assert palette[0] == pytest.approx((220, 20, 20), abs=3)
    assert (0, 0, 0) in palette


def test_make_palette_requires_black_option_for_all_dark_samples() -> None:
    with pytest.raises(ValueError, match="--include-black"):
        make_palette([_frame((0, 0, 0))])


def test_render_palette_creates_equal_width_horizontal_swatches() -> None:
    image = render_palette(
        [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        width=9,
        height=4,
    )

    assert image.size == (9, 4)
    assert image.getpixel((0, 0)) == (255, 0, 0)
    assert image.getpixel((3, 0)) == (0, 255, 0)
    assert image.getpixel((6, 0)) == (0, 0, 255)


def test_render_palette_svg_uses_vector_rectangles() -> None:
    import xml.etree.ElementTree as ET

    svg = render_palette_svg(
        [(255, 0, 0), (0, 255, 0), (0, 0, 255)],
        width=9,
        height=4,
    )
    root = ET.fromstring(svg)
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    rectangles = root.findall("./svg:rect", namespace)

    assert len(rectangles) == 3
    assert [rect.attrib["fill"] for rect in rectangles] == [
        "#ff0000",
        "#00ff00",
        "#0000ff",
    ]
