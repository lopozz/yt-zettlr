import argparse
import json
import re
from pathlib import Path

import requests

from src.extraction import (
    extract_chapter_start_ids,
    extract_chapter_titles,
    extract_idea_title,
    extract_ideas,
)
from src.prompts import (
    CHAPTER_ID_PROMPT,
    CHAPTER_TITLE_PROMPT,
    IDEA_PROMPT,
    IDEA_TITLE_PROMPT,
    TAKEAWAY_ID_PROMPT,
)

DEFAULT_MODEL = "mistralai/Ministral-3-3B-Instruct-2512"
DEFAULT_URL = "http://0.0.0.0:8000/v1/chat/completions"
TITLE_PATTERN = re.compile(r"^Chapter\s+\d+:\s*(.+)$", re.MULTILINE)
START_ID_PATTERN = re.compile(r"^Chapter\s+\d+\s*[:]*\s*\[(\d+)\]\s*$", re.MULTILINE)
NUMBERED_LIST_PATTERN = re.compile(r"^\s*\d+\.\s+(.*?)\s*$", re.MULTILINE)
REFERENCE_PATTERN = re.compile(r"(\d+)(?:[-–—](\d+))?")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a chapter and idea structure from a transcript JSON file."
    )
    parser.add_argument("input", type=Path, help="Path to the transcript JSON file.")
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
        "--url",
        default=DEFAULT_URL,
        help=f"Chat completion endpoint. Default: {DEFAULT_URL}",
    )
    return parser.parse_args()


def load_transcript(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def extract_titles(segments: list[dict], model: str, url: str) -> list[str]:
    # Step 1: Ask the model to split the transcript into chapter titles.
    context = "\n".join(segment["text"] for segment in segments)
    response = extract_chapter_titles(
        CHAPTER_TITLE_PROMPT.format(context=context),
        model=model,
        url=url,
    )
    return TITLE_PATTERN.findall(response)


def extract_start_ids(
    segments: list[dict], titles: list[str], model: str, url: str
) -> list[int]:
    # Step 2: Ask the model for the segment index where each chapter starts.
    context = "\n".join(f"[{index}] {segment['text']}" for index, segment in enumerate(segments))
    prompt = CHAPTER_ID_PROMPT.format(
        context=context,
        titles="\n".join(
            f"Chapter {index}: {title}" for index, title in enumerate(titles, start=1)
        ),
    )
    response = extract_chapter_start_ids(prompt, model=model, url=url)
    return [int(start_id) for start_id in START_ID_PATTERN.findall(response)]


def build_chapters(
    segments: list[dict], titles: list[str], start_ids: list[int]
) -> list[dict]:
    # Step 3: Combine titles and start indices into explicit chapter ranges.
    if len(titles) != len(start_ids):
        raise ValueError(f"Chapter/title mismatch: {len(start_ids)} != {len(titles)}")
    if any(start_ids[index] >= start_ids[index + 1] for index in range(len(start_ids) - 1)):
        raise ValueError(f"Chapter start ids are not strictly increasing: {start_ids}")

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


def build_reference_groups(reference_text: str) -> list[list[int]]:
    # Step 4: Expand model-generated ids and ranges into explicit segment groups.
    groups = []
    for start, end in REFERENCE_PATTERN.findall(reference_text):
        if end:
            groups.append(list(range(int(start), int(end) + 1)))
        else:
            groups.append([int(start)])
    return groups


def fetch_idea_references(
    chapter: dict, idea_description: str, chapter_offset: int, model: str, url: str
) -> list[list[int]]:
    # Step 5: Retrieve transcript references that support each idea.
    context = "\n".join(
        f"[{index + chapter_offset}] {segment}"
        for index, segment in enumerate(chapter["segments"])
    )
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": TAKEAWAY_ID_PROMPT.format(
                            context=context,
                            concept=idea_description,
                        ),
                    }
                ],
            }
        ],
    }
    response = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json=payload,
    )
    response.raise_for_status()
    reference_text = response.json()["choices"][0]["message"]["content"]
    return build_reference_groups(reference_text)


def extract_chapter_ideas(chapters: list[dict], transcript: list[dict], model: str, url: str) -> None:
    # Step 6: Extract ideas for each chapter, then attach titles, quotes, and timestamps.
    for chapter_index, chapter in enumerate(chapters, start=1):
        print(f"Processing chapter {chapter_index}/{len(chapters)} [{chapter['title']}]")

        chapter_context = " ".join(chapter["segments"])
        ideas_response = extract_ideas(
            IDEA_PROMPT.format(title=chapter["title"], context=chapter_context),
            model=model,
            url=url,
        )
        idea_descriptions = NUMBERED_LIST_PATTERN.findall(ideas_response)

        chapter_offset = chapter["start"]
        structured_ideas = []
        for idea_description in idea_descriptions:
            title_prompt = IDEA_TITLE_PROMPT.format(
                context=chapter_context,
                title=idea_description,
            )
            idea_title = extract_idea_title(title_prompt, model=model, url=url).replace("*", "").strip()
            reference_groups = fetch_idea_references(
                chapter,
                idea_description,
                chapter_offset,
                model,
                url,
            )

            timestamps = []
            quotes = []
            for id_group in reference_groups:
                timestamps_group = []
                quote_group = []
                for segment_id in id_group:
                    segment = transcript[segment_id]
                    timestamps_group.append((segment["start"], segment["end"]))
                    quote_group.append(segment["text"])
                timestamps.append(timestamps_group)
                quotes.append(quote_group)

            structured_ideas.append(
                {
                    "title": idea_title,
                    "description": idea_description,
                    "quotes": quotes,
                    "timestamps": timestamps,
                }
            )

        chapter["ideas"] = structured_ideas


def default_output_path(input_path: Path) -> Path:
    return input_path.with_suffix(".zttlr.json")


def main() -> None:
    args = parse_args()

    # Step 0: Load the transcript data that drives the whole pipeline.
    transcript = load_transcript(args.input)

    # Step 1: Extract the chapter boundaries from the transcript.
    titles = extract_titles(transcript, model=args.model, url=args.url)
    start_ids = extract_start_ids(transcript, titles, model=args.model, url=args.url)
    chapters = build_chapters(transcript, titles, start_ids)

    # Step 2: Extract structured ideas and supporting references for each chapter.
    extract_chapter_ideas(chapters, transcript, model=args.model, url=args.url)

    # Step 3: Persist the final structured result as JSON.
    output_path = args.output or default_output_path(args.input)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(chapters, handle, indent=2, ensure_ascii=False)

    print(f"Saved structured output to {output_path}")


if __name__ == "__main__":
    main()
