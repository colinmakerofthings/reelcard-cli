"""Representative frame colors and plain chronological barcode images."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Literal

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

from reelcard.video import VideoFrame

DEFAULT_TRIM_FRACTION = 0.1
DEFAULT_BARCODE_HEIGHT = 64
BRIGHT_PIXEL_FRACTION = 0.75
ColorStyle = Literal["natural", "brighter", "vivid"]
PALETTE_SIZE = 6
PALETTE_SAMPLE_SIZE = 16
NEAR_BLACK_THRESHOLD = 24


def representative_color(
    frame: VideoFrame,
    *,
    trim_fraction: float = DEFAULT_TRIM_FRACTION,
) -> tuple[int, int, int]:
    """Calculate a robust color from the brighter three-quarters of a frame.

    Keeping darker pixels out of the color estimate reduces shadow bias. A
    trimmed channel mean over the retained pixels limits the effect of
    highlights and isolated color noise.
    """
    if not isinstance(frame, VideoFrame):
        raise TypeError("frame must be a VideoFrame")
    if (
        isinstance(frame.width, bool)
        or not isinstance(frame.width, int)
        or frame.width <= 0
        or isinstance(frame.height, bool)
        or not isinstance(frame.height, int)
        or frame.height <= 0
    ):
        raise ValueError("frame dimensions must be positive integers")
    if len(frame.rgb) != frame.width * frame.height * 3:
        raise ValueError("frame RGB data length does not match its dimensions")
    if (
        isinstance(trim_fraction, bool)
        or not isinstance(trim_fraction, (int, float))
        or not math.isfinite(trim_fraction)
        or not 0 <= trim_fraction < 0.5
    ):
        raise ValueError("trim_fraction must be finite and in the range [0, 0.5)")

    pixels = np.frombuffer(frame.rgb, dtype=np.uint8).reshape(-1, 3)
    keep_count = max(1, math.ceil(len(pixels) * BRIGHT_PIXEL_FRACTION))
    brightness = pixels.max(axis=1)
    brightest_indices = np.argsort(brightness, kind="stable")[-keep_count:]
    members = pixels[brightest_indices]
    trim_count = int(len(members) * trim_fraction)
    sorted_channels = np.sort(members, axis=0)
    retained = sorted_channels[trim_count : len(members) - trim_count or None]
    means = retained.mean(axis=0, dtype=np.float64)
    rounded = np.floor(means + 0.5).astype(np.uint8)
    return int(rounded[0]), int(rounded[1]), int(rounded[2])


def make_barcode(
    frames: Iterable[VideoFrame],
    *,
    height: int = DEFAULT_BARCODE_HEIGHT,
    color_style: ColorStyle = "natural",
) -> Image.Image:
    """Render sampled frames as one vertical stripe each, in input order."""
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError("barcode height must be a positive integer")
    if color_style not in ("natural", "brighter", "vivid"):
        raise ValueError(
            "color_style must be 'natural', 'brighter', or 'vivid'"
        )

    colors: list[tuple[int, int, int]] = []
    previous_timestamp = -math.inf
    for frame in frames:
        if (
            isinstance(frame.timestamp, bool)
            or not isinstance(frame.timestamp, (int, float))
            or not math.isfinite(frame.timestamp)
            or frame.timestamp < 0
        ):
            raise ValueError("frame timestamps must be finite and non-negative")
        if frame.timestamp < previous_timestamp:
            raise ValueError("frames must be supplied in chronological order")
        previous_timestamp = frame.timestamp
        colors.append(representative_color(frame))

    if not colors:
        raise ValueError("at least one frame is required to make a barcode")

    row = bytes(channel for color in colors for channel in color)
    barcode = Image.frombytes("RGB", (len(colors), height), row * height)
    if color_style == "brighter":
        barcode = ImageEnhance.Brightness(barcode).enhance(1.15)
    elif color_style == "vivid":
        barcode = ImageEnhance.Color(barcode).enhance(1.25)
    return barcode


def make_palette(
    frames: Iterable[VideoFrame],
    *,
    include_black: bool = False,
) -> list[tuple[int, int, int]]:
    """Extract up to six prominent, perceptually distinct colors from sampled frames."""
    if not isinstance(include_black, bool):
        raise ValueError("include_black must be a boolean")

    samples: list[np.ndarray] = []
    previous_timestamp = -math.inf
    for frame in frames:
        if (
            isinstance(frame.timestamp, bool)
            or not isinstance(frame.timestamp, (int, float))
            or not math.isfinite(frame.timestamp)
            or frame.timestamp < 0
        ):
            raise ValueError("frame timestamps must be finite and non-negative")
        if frame.timestamp < previous_timestamp:
            raise ValueError("frames must be supplied in chronological order")
        previous_timestamp = frame.timestamp
        if (
            isinstance(frame.width, bool)
            or not isinstance(frame.width, int)
            or frame.width <= 0
            or isinstance(frame.height, bool)
            or not isinstance(frame.height, int)
            or frame.height <= 0
            or len(frame.rgb) != frame.width * frame.height * 3
        ):
            raise ValueError("frame RGB data length does not match its dimensions")

        image = Image.frombytes("RGB", (frame.width, frame.height), frame.rgb)
        image.thumbnail((PALETTE_SAMPLE_SIZE, PALETTE_SAMPLE_SIZE), Image.Resampling.BOX)
        pixels = np.asarray(image, dtype=np.uint8).reshape(-1, 3)
        if not include_black:
            pixels = pixels[pixels.max(axis=1) > NEAR_BLACK_THRESHOLD]
        if len(pixels):
            samples.append(pixels)

    if not samples:
        if include_black:
            raise ValueError("at least one frame is required to make a palette")
        raise ValueError(
            "all sampled pixels were near-black; use --include-black to include them"
        )

    rgb_pixels = np.concatenate(samples, axis=0)
    lab_pixels = _rgb_to_lab(rgb_pixels)
    colors, counts = np.unique(
        lab_pixels.round().astype(np.int16),
        axis=0,
        return_counts=True,
    )
    centers = _cluster_lab_colors(colors.astype(np.float64), counts, PALETTE_SIZE)
    labels = _nearest_centers(colors, centers)
    prominence = np.bincount(labels, weights=counts, minlength=len(centers))
    order = np.argsort(-prominence, kind="stable")
    return [_lab_to_rgb(centers[index]) for index in order]


def _cluster_lab_colors(
    colors: np.ndarray,
    weights: np.ndarray,
    count: int,
) -> np.ndarray:
    center_count = min(count, len(colors))
    centers = [colors[int(np.argmax(weights))]]
    while len(centers) < center_count:
        distances = np.min(
            np.stack([np.sum((colors - center) ** 2, axis=1) for center in centers]),
            axis=0,
        )
        weighted_distances = distances * np.sqrt(weights / weights.max())
        already_selected = np.asarray(
            [np.all(colors == center, axis=1) for center in centers]
        ).any(axis=0)
        weighted_distances[already_selected] = 0
        centers.append(colors[int(np.argmax(weighted_distances))])

    center_array = np.asarray(centers, dtype=np.float64)
    for _ in range(20):
        labels = _nearest_centers(colors, center_array)
        updated = center_array.copy()
        for index in range(center_count):
            members = labels == index
            if members.any():
                updated[index] = np.average(colors[members], axis=0, weights=weights[members])
        if np.allclose(updated, center_array):
            break
        center_array = updated
    labels = _nearest_centers(colors, center_array)
    occupied = np.bincount(labels, minlength=center_count) > 0
    return center_array[occupied]


def _nearest_centers(colors: np.ndarray, centers: np.ndarray) -> np.ndarray:
    distances = np.sum((colors[:, None, :] - centers[None, :, :]) ** 2, axis=2)
    return np.argmin(distances, axis=1)


def _rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    srgb = rgb.astype(np.float64) / 255.0
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array(
        [
            [0.4124564, 0.2126729, 0.0193339],
            [0.3575761, 0.7151522, 0.1191920],
            [0.1804375, 0.0721750, 0.9503041],
        ]
    )
    xyz /= np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    transformed = np.where(
        xyz > delta**3,
        np.cbrt(xyz),
        xyz / (3 * delta**2) + 4 / 29,
    )
    x, y, z = transformed.T
    return np.column_stack((116 * y - 16, 500 * (x - y), 200 * (y - z)))


def _lab_to_rgb(lab: np.ndarray) -> tuple[int, int, int]:
    fy = (lab[0] + 16) / 116
    fx = lab[1] / 500 + fy
    fz = fy - lab[2] / 200
    delta = 6 / 29
    transformed = np.array([fx, fy, fz])
    xyz = np.where(
        transformed > delta,
        transformed**3,
        3 * delta**2 * (transformed - 4 / 29),
    )
    xyz *= np.array([0.95047, 1.0, 1.08883])
    linear = xyz @ np.array(
        [
            [3.2404542, -0.9692660, 0.0556434],
            [-1.5371385, 1.8760108, -0.2040259],
            [-0.4985314, 0.0415560, 1.0572252],
        ]
    )
    srgb = np.where(
        linear <= 0.0031308,
        linear * 12.92,
        1.055 * np.maximum(linear, 0) ** (1 / 2.4) - 0.055,
    )
    channels = np.floor(np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)
    return int(channels[0]), int(channels[1]), int(channels[2])


def render_palette(
    colors: list[tuple[int, int, int]],
    *,
    width: int,
    height: int,
) -> Image.Image:
    """Render palette colors as equal-width vertical swatches."""
    if not colors:
        raise ValueError("palette must contain at least one color")
    if any(
        len(color) != 3
        or any(
            isinstance(channel, bool)
            or not isinstance(channel, int)
            or not 0 <= channel <= 255
            for channel in color
        )
        for color in colors
    ):
        raise ValueError("palette colors must be RGB integer triples")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
    ):
        raise ValueError("palette dimensions must be positive integers")
    if width < len(colors):
        raise ValueError("palette width must be at least the number of colors")

    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    for index, color in enumerate(colors):
        left = index * width // len(colors)
        right = (index + 1) * width // len(colors)
        draw.rectangle((left, 0, right - 1, height - 1), fill=color)
    return image


def render_palette_svg(
    colors: list[tuple[int, int, int]],
    *,
    width: int,
    height: int,
    dpi: float = 300,
) -> str:
    """Render palette swatches as a vector SVG document."""
    if not colors:
        raise ValueError("palette must contain at least one color")
    if (
        isinstance(width, bool)
        or not isinstance(width, int)
        or width <= 0
        or isinstance(height, bool)
        or not isinstance(height, int)
        or height <= 0
    ):
        raise ValueError("palette dimensions must be positive integers")
    if width < len(colors):
        raise ValueError("palette width must be at least the number of colors")
    if (
        isinstance(dpi, bool)
        or not isinstance(dpi, (int, float))
        or not math.isfinite(dpi)
        or dpi <= 0
    ):
        raise ValueError("DPI must be a positive finite number")
    physical_width = width / dpi * 25.4
    physical_height = height / dpi * 25.4
    rectangles = []
    for index, color in enumerate(colors):
        if len(color) != 3 or any(
            isinstance(channel, bool)
            or not isinstance(channel, int)
            or not 0 <= channel <= 255
            for channel in color
        ):
            raise ValueError("palette colors must be RGB integer triples")
        left = index * width // len(colors)
        right = (index + 1) * width // len(colors)
        fill = f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"
        rectangles.append(
            f'<rect x="{left}" y="0" width="{right - left}" '
            f'height="{height}" fill="{fill}"/>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{physical_width:.4f}mm" height="{physical_height:.4f}mm" '
        f'viewBox="0 0 {width} {height}" role="img">'
        "<title>Film color palette</title>"
        + "".join(rectangles)
        + "</svg>"
    )
