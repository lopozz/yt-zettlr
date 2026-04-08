import re
import requests

from openai import OpenAI
from yt_dlp import YoutubeDL

client = OpenAI(
    api_key="dummy-key",  # many local OpenAI-compatible servers accept any string here
    base_url="http://0.0.0.0:8000/v1",
)


def extract_chapters_yt_dlp(url: str):
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    chapters = info.get("chapters")
    if chapters is None or len(chapters) < 2:
        print("No explicit chapters found.")
        return None

    result = []
    for ch in chapters:
        result.append(
            {
                "title": ch["title"].strip(),
                "start_time": ch["start_time"],
                "end_time": ch["end_time"],
            }
        )

    return result


def openai_chat_completion_client(
    prompt: str,
    temperature: float = 0.1,
    model: str = "mistralai/Ministral-3-3B-Instruct-2512",
) -> str:
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
    )
    return response.choices[0].message.content
