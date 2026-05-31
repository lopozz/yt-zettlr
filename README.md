# Queen

Queen turns the subtitles of a YouTube video into a small Zettelkasten-style
knowledge base. It is intended for extracting durable notes from talks,
lectures, and long-form videos without manually reviewing the full transcript.

The pipeline:

1. Downloads available subtitles or auto-generated captions with `yt-dlp`.
2. Joins fragmented caption events into sentence-level transcript entries.
3. Uses a local OpenAI-compatible LLM to identify chapters and key ideas.
4. Resolves each idea back to supporting transcript excerpts.
5. Writes one Markdown note per idea, including timestamped YouTube links.

## Requirements

- Python 3.12 or newer
- [`uv`](https://docs.astral.sh/uv/)
- [Deno](https://docs.deno.com/runtime/getting_started/installation/) 2.3.0 or
  newer, used by `yt-dlp` to solve YouTube JavaScript challenges
- Docker
- An NVIDIA GPU and the NVIDIA container runtime

Install the Python dependencies:

```bash
uv sync
```

Install Deno on Linux or macOS, then restart the shell:

```bash
curl -fsSL https://deno.land/install.sh | sh
exec "$SHELL"
deno --version
```

Deno is required by `yt-dlp`, not by Queen's Python code. YouTube may protect
subtitle requests with JavaScript challenges. `yt-dlp` uses Deno to execute its
EJS challenge solver scripts and obtain the subtitle files before Queen starts
extracting notes. Without a supported JavaScript runtime, subtitle downloads
may fail with `challenge solving failed`.

## Start the LLM

The extraction script expects an OpenAI-compatible API at
`http://0.0.0.0:8000`. Start the default model with vLLM:

```bash
docker run --rm \
  --runtime nvidia \
  --name "Ministral-3-3B-Instruct-2512" \
  --gpus all \
  --ipc=host \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -p 8000:8000 \
  vllm/vllm-openai:v0.15.1 \
  --model "mistralai/Ministral-3-3B-Instruct-2512" \
  --dtype bfloat16 \
  --tensor-parallel-size 1 \
  --max-model-len 5000 \
  --gpu-memory-utilization 0.9
```

The first start downloads the model into the mounted Hugging Face cache.

## Generate Notes

Run the main pipeline from the repository root:

```bash
uv run python -m scripts.main_zttlr \
  --yt-url "https://www.youtube.com/watch?v=VIDEO_ID"
```

English subtitles are downloaded by default. For a video in another language,
pass its subtitle language code. For example, use `it` for Italian:

```bash
uv run python -m scripts.main_zttlr \
  --yt-url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --sub-lang it
```

The script checks that the local LLM is healthy before downloading captions.
Generated files are written under `z/`, which is ignored by Git:

```text
z/
├── Video_Title.LANGUAGE.json3
├── Video_Title.LANGUAGE.json
└── Video_Title/
    ├── 0_First_Chapter/
    │   ├── 0_first_idea.md
    │   └── 1_second_idea.md
    └── 1_Second_Chapter/
        └── 2_another_idea.md
```

Each Markdown note contains the extracted takeaway, supporting excerpts, links
to the relevant timestamps in the source video, and a reference to the video.

To use another model already served by the same local vLLM instance, pass its
identifier:

```bash
uv run python -m scripts.main_zttlr \
  --yt-url "https://www.youtube.com/watch?v=VIDEO_ID" \
  --model "your-model-id"
```

If `yt-dlp` reports `challenge solving failed`, confirm that Deno is available:

```bash
deno --version
uv sync
```

`yt-dlp` detects Deno automatically when it is on `PATH`. The project installs
`yt-dlp[default]`, which includes the matching EJS challenge solver scripts.

## Convert Captions Only

The caption converter can also be used independently. Given a local `.json3`
subtitle file, it writes a sentence-level `.json` transcript beside it:

```bash
uv run python -m scripts.main_captios \
  --input path/to/subtitles.LANGUAGE.json3
```

## Current Scope

- The main pipeline prefers the most recently modified `.json3` subtitle file
  matching `--sub-lang`.
- The LLM endpoint is currently fixed to `http://0.0.0.0:8000`.
- Notes are written to the repository-local `z/` directory.
