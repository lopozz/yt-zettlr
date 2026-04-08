import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")

def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert fragmented SRT subtitles into sentence-level JSON."
    )
    parser.add_argument("-i", "--input", help="Path to a local .srt file")

    return parser.parse_args()


def ms_to_timestamp(ms: int) -> str:
    total_seconds, milliseconds = divmod(ms, 1000)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def build_sentences(events):
    sentences = []
    current_text = ""
    current_start = None
    current_end = None

    for event in events:
        event_start = event["tStartMs"]

        for seg in event.get("segs", []):
            text = seg.get("utf8", "")
            if not text:
                continue

            seg_offset = seg.get("tOffsetMs", 0)
            seg_time = event_start + seg_offset

            if current_start is None and text.strip():
                current_start = seg_time

            current_text += text
            current_end = seg_time

            stripped = current_text.strip()
            if stripped and SENTENCE_END_RE.search(stripped):
                sentences.append({
                    "text": stripped.replace('\n', ' '),
                    "start": ms_to_timestamp(current_start),
                    "end": ms_to_timestamp(current_end),
                })
                current_text = ""
                current_start = None
                current_end = None

    if current_text.strip():
        sentences.append({
            "text": current_text.strip(),
            "start": ms_to_timestamp(current_start),
            "end": ms_to_timestamp(current_end),
        })

    return sentences


def main():
    args = parse_args()
    source = Path(args.input)

    if source.suffix.lower() != ".json3":
        raise SystemExit("Source must be an .json3 file.")
    if not source.exists():
        raise SystemExit(f"File not found: {source}")

    with open(source) as f:
        events = json.load(f)['events']

    sentences = build_sentences(events)
    output_path = source.with_suffix(".json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sentences, f, ensure_ascii=False, indent=2)

    print(f"Saved to {output_path}")



if __name__ == "__main__":
    main()
