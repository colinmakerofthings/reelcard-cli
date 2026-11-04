---
name: reelcard-usage
description: Help people install and run Reelcard, choose CLI options, and troubleshoot common setup or command errors. Use when someone wants to make a film-barcode poster, needs a Reelcard command for a video or movie series, or asks how to install or use this repository's CLI.
---

# Reelcard usage

Help the user get from their goal and video files to a correct `reelcard` command. Prefer a short, tailored command and explain only the options that matter. Do not invent file paths, metadata, or installation state; ask for missing details when needed. Do not run a poster-generation command unless the user asks you to run it.

## Check prerequisites

- Reelcard requires Python 3.11+ and separately installed FFmpeg and FFprobe on `PATH`.
- For source installation, follow the repository README: create and activate a virtual environment, then run `python -m pip install .`. Use the activation and path syntax for the user's shell and operating system.
- If the command is not found after installation, check that the virtual environment is active and that its scripts directory is on `PATH`.
- To diagnose FFmpeg setup, suggest `ffmpeg -version` and `ffprobe -version` in a new terminal. Installing the Python package does not install these programs.
- The tool processes video locally. It only contacts OMDb when the user requests lookup with `--imdb-id` or a series manifest entry containing `imdb_id`.

## Build commands safely

- Quote input paths and output paths, especially when they contain spaces. Use syntax appropriate to the user's shell.
- A single video is the positional input. Without `--title`, the filename supplies the title. Default output is a sanitized title-based PNG in the current directory.
- Existing outputs are not replaced by default. Choose a new `--output` path or add `--force` only when the user intends to overwrite.
- PNG is the default; for SVG, pass both `--format svg` and an `.svg` output path.
- Use `--stripes` to control sampled frames (default 300, maximum 10000), and `--color-style natural|brighter|vivid` to change barcode treatment.
- `--palette` makes a color-palette poster; `--include-black` is valid only with `--palette`.
- Custom dimensions require both `--width` and `--height` and must be landscape. The postcard preset is the default.
- For optional OMDb metadata, use an IMDb ID and the `OMDB_API_KEY` environment variable. Do not ask the user to paste an API key into chat; show how to configure it in their shell if needed. Manual metadata works without lookup.

## Common command patterns

Basic poster:

```console
reelcard "My Film.mp4"
```

Set metadata, output path, and sampling:

```console
reelcard "My Film.mp4" --title "My Film" --year 1994 --stripes 600 --output "my-film.png"
```

Use SVG, a palette, or IMDb lookup:

```console
reelcard "My Film.mp4" --format svg --output "my-film.svg"
reelcard "My Film.mp4" --palette --include-black
reelcard "My Film.mp4" --imdb-id tt0087182
```

For multiple films, use `--series PATH` with a JSON manifest. Each movie needs a path relative to the manifest and a `year` or `imdb_id`; paths and per-movie metadata belong in the manifest, not in command-line metadata flags. The result is stacked in chronological order:

```console
reelcard --series "my-series.json" --output "my-series.png"
```

Use `reelcard --help` for the installed version's options. If troubleshooting, start with the exact command and error, then check the input file, FFmpeg/FFprobe availability, output directory, matching output extension, and whether the output already exists. Never recommend `--force` as a generic fix without clarifying that it overwrites an existing poster.
