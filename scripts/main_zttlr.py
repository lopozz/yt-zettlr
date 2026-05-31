import re
import os
import json
import argparse
import subprocess

from pathlib import Path
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from src.extraction import openai_chat_completion_client
from src.llm_engine_utils import check_health
from src.prompts import (
    CHAPTER_ID_PROMPT,
    CHAPTER_TITLE_PROMPT,
    IDEA_PROMPT,
    IDEA_TITLE_PROMPT,
    IDEA_ID_PROMPT,
)
from scripts.main_captios import build_sentences

from src.zttlr import save_note_to_zettelkasten

DEFAULT_MODEL = "mistralai/Ministral-3-3B-Instruct-2512"
DEFAULT_URL = "http://0.0.0.0:8000"
TITLE_PATTERN = re.compile(r"^Chapter\s+\d+:\s*(.+)$", re.MULTILINE)
START_ID_PATTERN = re.compile(r"^Chapter\s+\d+\s*[:]*\s*\[(\d+)\]\s*$", re.MULTILINE)
NUMBERED_LIST_PATTERN = re.compile(r"^\s*\d+\.\s+(.*?)\s*$", re.MULTILINE)
REFERENCE_PATTERN = re.compile(r"(\d+)(?:[-–—](\d+))?")
SHELL_ESCAPED_URL_CHARACTER_PATTERN = re.compile(r"\\([?=&])")


def build_progress() -> Progress:
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a chapter and idea structure from a transcript JSON file."
    )
    parser.add_argument("--yt-url", required=True, help="URL of the youtube video.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Optional output path for the structured JSON result.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Chat completion model to use. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--sub-lang",
        default="en",
        help="Subtitle language code to download, such as en or it. Default: en",
    )
    return parser.parse_args()


def load_transcript(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def video_title_from_subtitle_path(source: Path, subtitle_language: str) -> str:
    language_suffix = f".{subtitle_language}.json3"
    if source.name.endswith(language_suffix):
        return source.name.removesuffix(language_suffix)
    return source.name.removesuffix(".json3")


def find_subtitle_source(output_dir: Path, subtitle_language: str) -> Path | None:
    matches = list(output_dir.glob(f"*.{subtitle_language}.json3"))
    if not matches:
        matches = list(output_dir.glob("*.json3"))
    return max(matches, key=lambda path: path.stat().st_mtime) if matches else None


def download_subtitles(
    yt_url: str,
    output_dir: Path,
    subtitle_language: str = "en",
) -> None:
    yt_url = SHELL_ESCAPED_URL_CHARACTER_PATTERN.sub(r"\1", yt_url)
    command = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-format",
        "json3",
        "--sub-langs",
        subtitle_language,
        "--restrict-filenames",
        "-o",
        str(output_dir / "%(title)s.%(ext)s"),
    ]
    command.append(yt_url)

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as error:
        details = (error.stderr or error.stdout or "No details provided.").strip()
        if "challenge solving failed" in details:
            details += (
                "\n\nYouTube requires a JavaScript challenge solver. Install Deno "
                "2.3.0 or newer and run uv sync so yt-dlp's EJS scripts are "
                "installed. Deno is detected automatically when it is on PATH."
            )
        raise SystemExit(f"yt-dlp failed to download subtitles:\n{details}") from error


def extract_titles(segments: list[dict], model: str) -> list[str]:
    # Step 1: Ask the model to split the transcript into chapter titles.
    prompt = CHAPTER_TITLE_PROMPT.format(
        context="\n".join(segment["text"] for segment in segments)
    )
    with build_progress() as progress:
        task_id = progress.add_task("Extracting chapter titles", total=1)
        content = openai_chat_completion_client(
            prompt,
            model=model,
        )
        progress.advance(task_id)
    return TITLE_PATTERN.findall(content)


def extract_start_ids(segments: list[dict], titles: list[str], model: str) -> list[int]:

    prompt = CHAPTER_ID_PROMPT.format(
        context="\n".join(
            f"[{index}] {segment['text']}" for index, segment in enumerate(segments)
        ),
        chapters="\n".join(
            f"Chapter {index}: {title}" for index, title in enumerate(titles, start=1)
        ),
    )
    with build_progress() as progress:
        task_id = progress.add_task("Extracting chapter boundaries", total=1)
        content = openai_chat_completion_client(prompt, model=model)
        progress.advance(task_id)
    return [int(start_id) for start_id in START_ID_PATTERN.findall(content)]


def normalize_start_ids(
    start_ids: list[int], titles: list[str], segment_count: int
) -> list[int]:
    if len(start_ids) != len(titles):
        raise ValueError(
            f"Chapter/title mismatch: {len(start_ids)} != {len(titles)}"
        )

    invalid_ids = [start_id for start_id in start_ids if not 0 <= start_id < segment_count]
    if invalid_ids:
        raise ValueError(
            f"Chapter start ids are outside the transcript: {invalid_ids}"
        )

    normalized_ids = sorted(start_ids)
    if len(set(normalized_ids)) != len(normalized_ids):
        raise ValueError(f"Chapter start ids are not unique: {start_ids}")

    return normalized_ids


def build_chapters(
    segments: list[dict], titles: list[str], start_ids: list[int]
) -> list[dict]:

    chapters = []
    for index, (title, start_id) in enumerate(zip(titles, start_ids)):
        end_id = len(segments) - 1
        if index < len(start_ids) - 1:
            end_id = start_ids[index + 1] - 1

        chapter_segments = segments[start_id : end_id + 1]
        chapters.append(
            {
                "start": start_id,
                "end": end_id,
                "start_ts": chapter_segments[0]["start"],
                "end_ts": chapter_segments[-1]["start"],
                "title": title,
                "segments": [segment["text"] for segment in chapter_segments],
            }
        )

    return chapters


def extract_chapter_ideas(chapters):
    chapter_ideas = []
    pattern = re.compile(r"^\s*\d+\.\s+(.*?)\s*$", re.MULTILINE)
    with build_progress() as progress:
        chapter_task = progress.add_task(
            "Extracting chapter ideas", total=len(chapters)
        )
        for ch in chapters:
            context = " ".join(ch["segments"])
            progress.update(
                chapter_task,
                description=f"Extracting ideas for {ch['title']}",
            )
            ideas = openai_chat_completion_client(
                IDEA_PROMPT.format(title=ch["title"], context=context), 0
            )
            ideas = pattern.findall(ideas)
            structured_ideas = []
            idea_task = progress.add_task(
                f"Refining idea titles for {ch['title']}",
                total=max(len(ideas), 1),
            )
            for idea in ideas:
                response = (
                    openai_chat_completion_client(
                        IDEA_TITLE_PROMPT.format(title=idea, context=context), 0
                    )
                    .replace("*", "")
                    .replace(".", "")
                )
                structured_ideas.append({"title": response, "description": idea})
                progress.advance(idea_task)

            if not ideas:
                progress.advance(idea_task)

            progress.remove_task(idea_task)
            chapter_ideas.append(structured_ideas)
            progress.advance(chapter_task)

    return chapter_ideas


def fetch_idea_references(chapter_ideas, chapters):
    chapter_references = []
    with build_progress() as progress:
        chapter_task = progress.add_task(
            "Fetching idea references", total=len(chapters)
        )
        for ideas, ch in zip(chapter_ideas, chapters):
            progress.update(
                chapter_task,
                description=f"Fetching references for {ch['title']}",
            )
            references = []
            offset = ch["start"]
            context = "\n".join(
                [f"[{i + offset}] {s}" for i, s in enumerate(ch["segments"])]
            )
            idea_task = progress.add_task(
                f"Resolving references for {ch['title']}",
                total=max(len(ideas), 1),
            )
            for idea in ideas:
                content = openai_chat_completion_client(
                    IDEA_ID_PROMPT.format(
                        context=context,
                        concept=idea["description"],
                    ),
                    0,
                )
                segments = re.findall(r"(\d+)(?:[-–—](\d+))?", content)

                reference = []

                for start, end in segments:
                    if end:
                        # 2. If there's an 'end' match, it's a range (e.g., 4-10)
                        # We add 1 to the end because range() is exclusive
                        reference.append(list(range(int(start), int(end) + 1)))
                    else:
                        # 3. Otherwise, it's a single ID
                        reference.append([int(start)])

                references.append(reference)
                progress.advance(idea_task)

            if not ideas:
                progress.advance(idea_task)

            progress.remove_task(idea_task)
            chapter_references.append(references)
            progress.advance(chapter_task)

    return chapter_references


def add_ideas_to_chapters(transcript, chapter_ideas, chapter_references, chapters):
    for ideas, references, ch in zip(chapter_ideas, chapter_references, chapters):
        ch["ideas"] = []
        for idea, references in zip(ideas, references):
            timestamps = []
            quotes = []
            for id_group in references:
                quote_group = []
                timestamps_group = []
                for id in id_group:
                    start, end = transcript[id]["start"], transcript[id]["end"]
                    timestamps_group.append((start, end))
                    quote_group.append(transcript[id]["text"])

                timestamps.append(timestamps_group)
                quotes.append(quote_group)
            ch["ideas"].append(
                {
                    "title": idea["title"],
                    "description": idea["description"],
                    "quotes": quotes,
                    "timestamps": timestamps,
                }
            )

    return chapters


def main() -> None:
    args = parse_args()

    if not check_health(DEFAULT_URL):
        raise SystemExit(
            f"LLM engine is not reachable at {DEFAULT_URL}. "
            "Start the container before running this script."
        )

    output_dir = Path.cwd() / "z"
    output_dir.mkdir(exist_ok=True)

    download_subtitles(
        args.yt_url,
        output_dir,
        subtitle_language=args.sub_lang,
    )

    source = find_subtitle_source(output_dir, args.sub_lang)

    if source is None:
        raise SystemExit("No .json3 subtitle file was produced by yt-dlp.")
    if source.suffix.lower() != ".json3":
        raise SystemExit("Source must be an .json3 file.")
    if not source.exists():
        raise SystemExit(f"File not found: {source}")

    with open(source) as f:
        events = json.load(f)["events"]

    sentences = build_sentences(events)
    output_path = source.with_suffix(".json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sentences, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")

    # Step 0: Load the transcript data that drives the whole pipeline.
    transcript = load_transcript(output_path)

    # Step 1: Extract the chapter boundaries from the transcript.
    titles = extract_titles(transcript, model=args.model)
    start_ids = extract_start_ids(transcript, titles, model=args.model)

    try:
        start_ids = normalize_start_ids(start_ids, titles, len(transcript))
    except ValueError as error:
        raise SystemExit(f"Invalid chapter boundaries returned by the model: {error}")

    chapters = build_chapters(transcript, titles, start_ids)
    chapter_ideas = extract_chapter_ideas(chapters)
    chapter_references = fetch_idea_references(chapter_ideas, chapters)
    chapters = add_ideas_to_chapters(
        transcript, chapter_ideas, chapter_references, chapters
    )

    c = 0
    video_title = video_title_from_subtitle_path(source, args.sub_lang)
    for i, ch in enumerate(chapters):
        chapter_dir_name = (
            f"{i}_{ch['title'].replace(' ', '_').replace('/', '_and_')}"
        )
        ch_dir = os.path.join(output_dir, video_title, chapter_dir_name)
        os.makedirs(ch_dir, exist_ok=True)
        for idea in ch["ideas"]:
            save_note_to_zettelkasten("purpose", c, idea, args.yt_url, ch_dir)
            c += 1

    print(f"Saved structured output to {output_path}")


if __name__ == "__main__":
    main()
