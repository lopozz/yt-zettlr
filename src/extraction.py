import re
import requests

from yt_dlp import YoutubeDL

# todo use openai client

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


def extract_chapter_titles(
    prompt,
    model="mistralai/Ministral-3-3B-Instruct-2512",
    url="http://0.0.0.0:8000/v1/chat/completions",
):
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


def extract_chapter_start_ids(
    prompt,
    model="mistralai/Ministral-3-3B-Instruct-2512",
    url="http://0.0.0.0:8000/v1/chat/completions",
):
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


def extract_ideas(
    prompt,
    model="mistralai/Ministral-3-3B-Instruct-2512",
    url="http://0.0.0.0:8000/v1/chat/completions",
):
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            }
        ],
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]


def extract_idea_title(
    prompt,
    model="mistralai/Ministral-3-3B-Instruct-2512",
    url="http://0.0.0.0:8000/v1/chat/completions",
):
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}],
            }
        ],
    }

    headers = {"Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()

    return response.json()["choices"][0]["message"]["content"]
