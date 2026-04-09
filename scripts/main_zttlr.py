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
    return parser.parse_args()


def load_transcript(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


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
        for n, (ideas, ch) in enumerate(zip(chapter_ideas, chapters)):
            progress.update(
                chapter_task,
                description=f"Fetching references for {ch['title']}",
            )
            references = []
            offset = (
                0 if n == 0 else sum(len(ch["segments"]) for ch in chapters[: n - 1])
            )
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

    command = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-format",
        "json3",
        "--restrict-filenames",
        "-o",
        str(output_dir / "%(title)s.%(ext)s"),
        args.yt_url,
    ]

    subprocess.run(command, check=True, capture_output=True, text=True)

    matches = list(output_dir.glob("*.json3"))
    source = matches[0] if matches else None

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

    assert all(
        [int(start_ids[i]) < int(start_ids[i + 1]) for i in range(len(start_ids) - 1)]
    ), f"Chapter start ids are not strictly increasing: {start_ids}"
    assert len(start_ids) == len(start_ids), (
        f"Chapter/title mismatch: {len(start_ids)} != {len(titles)}"
    )

    chapters = build_chapters(transcript, titles, start_ids)
    chapter_ideas = extract_chapter_ideas(chapters)
    chapter_references = fetch_idea_references(chapter_ideas, chapters)
    chapters = add_ideas_to_chapters(
        transcript, chapter_ideas, chapter_references, chapters
    )

    c = 0
    video_title = source.name.removesuffix(".en.json3")
    for i, ch in enumerate(chapters):
        ch_dir = os.path.join(
            output_dir, video_title, f"{i}_{ch['title'].replace(' ', '_')}"
        )
        if not os.path.exists(ch_dir):
            os.makedirs(ch_dir)
        for idea in ch["ideas"]:
            save_note_to_zettelkasten("purpose", c, idea, args.yt_url, ch_dir)
            c += 1

    print(f"Saved structured output to {output_path}")


if __name__ == "__main__":
    main()
