import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.main_zttlr import (
    download_subtitles,
    fetch_idea_references,
    find_subtitle_source,
    normalize_start_ids,
    video_title_from_subtitle_path,
)


class VideoTitleFromSubtitlePathTest(unittest.TestCase):
    def test_removes_italian_subtitle_suffix(self):
        title = video_title_from_subtitle_path(Path("Video_Title.it.json3"), "it")

        self.assertEqual(title, "Video_Title")

    def test_falls_back_to_removing_json3_suffix(self):
        title = video_title_from_subtitle_path(Path("Video_Title.json3"), "it")

        self.assertEqual(title, "Video_Title")


class FindSubtitleSourceTest(unittest.TestCase):
    def test_prefers_requested_language(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "Older.it.json3").touch()
            (output_dir / "Newer.en.json3").touch()

            source = find_subtitle_source(output_dir, "it")

        self.assertEqual(source.name, "Older.it.json3")


class NormalizeStartIdsTest(unittest.TestCase):
    def test_orders_valid_model_output(self):
        start_ids = normalize_start_ids([2, 21, 10], ["One", "Two", "Three"], 30)

        self.assertEqual(start_ids, [2, 10, 21])

    def test_rejects_duplicate_model_output(self):
        with self.assertRaisesRegex(ValueError, "not unique"):
            normalize_start_ids([2, 2], ["One", "Two"], 30)

    def test_rejects_out_of_range_model_output(self):
        with self.assertRaisesRegex(ValueError, "outside the transcript"):
            normalize_start_ids([2, 30], ["One", "Two"], 30)


class FetchIdeaReferencesTest(unittest.TestCase):
    @patch("scripts.main_zttlr.openai_chat_completion_client")
    def test_uses_chapter_start_as_segment_id_offset(self, completion):
        completion.side_effect = ["0", "2"]
        chapters = [
            {"title": "One", "start": 0, "segments": ["first", "second"]},
            {"title": "Two", "start": 2, "segments": ["third", "fourth"]},
        ]
        ideas = [
            [{"description": "first idea"}],
            [{"description": "second idea"}],
        ]

        fetch_idea_references(ideas, chapters)

        second_prompt = completion.call_args_list[1].args[0]
        self.assertIn("[2] third\n[3] fourth", second_prompt)


class DownloadSubtitlesTest(unittest.TestCase):
    @patch("scripts.main_zttlr.subprocess.run")
    def test_removes_shell_escaping_from_url_punctuation(self, run):
        download_subtitles(
            r"https://www.youtube.com/watch\?v\=TTIwVQQGG3Y\&feature\=shared",
            Path("/tmp/subtitles"),
        )

        command = run.call_args.args[0]
        self.assertEqual(
            command[-1],
            "https://www.youtube.com/watch?v=TTIwVQQGG3Y&feature=shared",
        )

    @patch("scripts.main_zttlr.subprocess.run")
    def test_passes_subtitle_language_to_yt_dlp(self, run):
        download_subtitles(
            "https://www.youtube.com/watch?v=TTIwVQQGG3Y",
            Path("/tmp/subtitles"),
            subtitle_language="it",
        )

        command = run.call_args.args[0]
        language_index = command.index("--sub-langs") + 1
        self.assertEqual(command[language_index], "it")

    @patch("scripts.main_zttlr.subprocess.run")
    def test_reports_yt_dlp_stderr(self, run):
        run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["yt-dlp"],
            stderr="ERROR: unsupported URL",
        )

        with self.assertRaisesRegex(
            SystemExit,
            "yt-dlp failed to download subtitles:\nERROR: unsupported URL",
        ):
            download_subtitles("https://example.com/video", Path("/tmp/subtitles"))

    @patch("scripts.main_zttlr.subprocess.run")
    def test_reports_javascript_challenge_recovery_options(self, run):
        run.side_effect = subprocess.CalledProcessError(
            returncode=1,
            cmd=["yt-dlp"],
            stderr="WARNING: n challenge solving failed",
        )

        with self.assertRaisesRegex(SystemExit, "Install Deno 2.3.0 or newer"):
            download_subtitles("https://example.com/video", Path("/tmp/subtitles"))


if __name__ == "__main__":
    unittest.main()
