import os
import json
from datetime import datetime


def timestamp_to_seconds(timestamp: str) -> float:
    dt = datetime.strptime(timestamp, "%H:%M:%S.%f")
    return dt.hour * 3600 + dt.minute * 60 + dt.second + dt.microsecond / 1_000_000


def save_note_to_zettelkasten(moc, id, data, reference, base_directory="zettelkasten"):
    """
    Takes a dictionary, creates a directory if needed, and saves a formatted
    Markdown file based on a specific Zettelkasten template.
    """

    file_title = (
        data["title"].replace(",", " ").replace(" ", "_").replace("/", "_and_").lower()
    )
    file_path = os.path.join(base_directory, f"{id}_{file_title}.md")
    content = data["description"]
    quotes = "\n".join(
        f"> [🎥]({reference}&t={int(timestamp_to_seconds(ts_group[0][0]))}s) {' '.join(quote_group)}"
        for ts_group, quote_group in zip(data["timestamps"], data["quotes"])
        if ts_group and ts_group[0]
    )
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    template = f"""{data["title"].lower()}
{timestamp}
Status: #idea
Tags: [[{moc}]]-{id}
---
{content}

{quotes}

---
# References
- {reference}

"""

    # 4. Write the file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(template)

    print(f"File saved successfully at: {file_path}")
