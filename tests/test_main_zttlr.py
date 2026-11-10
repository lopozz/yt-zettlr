import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from yt_dlp.utils import DownloadError

from scripts.main_zttlr import (
    download_subtitles,
    fetch_idea_references,
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
    @patch("scripts.main_zttlr.openai_chat_completion")
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

        fetch_idea_references(MagicMock(), ideas, chapters, "model")

        second_prompt = completion.call_args_list[1].args[2]
        self.assertIn("[2] third\n[3] fourth", second_prompt)


def fake_youtube_dl(info=None, error=None, raw=None):
    ydl = MagicMock()
    ydl.__enter__.return_value = ydl
    ydl.extract_info.return_value = raw if raw is not None else {
        "automatic_captions": {"en": [{"url": "https://yt/api/timedtext?v=1"}]},
        "subtitles": {},
    }
    if error:
        ydl.process_ie_result.side_effect = error
    else:
        ydl.process_ie_result.return_value = info
    return ydl


def info_with_subtitle(language="en", path="/tmp/subtitles/Video.en.json3"):
    return {"requested_subtitles": {language: {"filepath": path}}}


class DownloadSubtitlesTest(unittest.TestCase):
    @patch("scripts.main_zttlr.YoutubeDL")
    def test_removes_shell_escaping_from_url_punctuation(self, youtube_dl):
        ydl = youtube_dl.return_value = fake_youtube_dl(info_with_subtitle())

        download_subtitles(
            r"https://www.youtube.com/watch\?v\=TTIwVQQGG3Y\&feature\=shared",
            Path("/tmp/subtitles"),
        )

        self.assertEqual(
            ydl.extract_info.call_args.args[0],
            "https://www.youtube.com/watch?v=TTIwVQQGG3Y&feature=shared",
        )

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_passes_subtitle_language_to_yt_dlp(self, youtube_dl):
        youtube_dl.return_value = fake_youtube_dl(
            info_with_subtitle("it"),
            raw={"subtitles": {"it": [{"url": "https://yt/api/timedtext?v=1"}]}},
        )

        download_subtitles(
            "https://www.youtube.com/watch?v=TTIwVQQGG3Y",
            Path("/tmp/subtitles"),
            subtitle_language="it",
        )

        options = youtube_dl.call_args.args[0]
        self.assertEqual(options["subtitleslangs"], ["it"])

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_returns_info_reported_by_yt_dlp(self, youtube_dl):
        info = info_with_subtitle("it", "/tmp/subtitles/Video.it.json3")
        youtube_dl.return_value = fake_youtube_dl(
            info, raw={"subtitles": {"it": [{"url": "https://yt/api/timedtext?v=1"}]}}
        )

        result = download_subtitles(
            "https://example.com/video", Path("/tmp/subtitles"), "it"
        )

        self.assertEqual(result, info)

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_fails_when_no_subtitle_was_written(self, youtube_dl):
        youtube_dl.return_value = fake_youtube_dl({"requested_subtitles": None})

        with self.assertRaisesRegex(SystemExit, "No .json3 subtitle file"):
            download_subtitles("https://example.com/video", Path("/tmp/subtitles"))

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_reports_yt_dlp_error(self, youtube_dl):
        youtube_dl.return_value = fake_youtube_dl(
            error=DownloadError("ERROR: unsupported URL")
        )

        with self.assertRaisesRegex(
            SystemExit,
            "yt-dlp failed to download subtitles:\nERROR: unsupported URL",
        ):
            download_subtitles("https://example.com/video", Path("/tmp/subtitles"))

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_reports_javascript_challenge_recovery_options(self, youtube_dl):
        youtube_dl.return_value = fake_youtube_dl(
            error=DownloadError("WARNING: n challenge solving failed")
        )

        with self.assertRaisesRegex(SystemExit, "Install Deno 2.3.0 or newer"):
            download_subtitles("https://example.com/video", Path("/tmp/subtitles"))

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_extracts_metadata_only_once(self, youtube_dl):
        ydl = youtube_dl.return_value = fake_youtube_dl(info_with_subtitle())

        download_subtitles("https://example.com/video", Path("/tmp/subtitles"))

        ydl.extract_info.assert_called_once()
        ydl.process_ie_result.assert_called_once()

    @patch("scripts.main_zttlr.YoutubeDL")
    def test_rejects_translated_only_language_before_downloading(self, youtube_dl):
        ydl = youtube_dl.return_value = fake_youtube_dl(
            raw={
                "subtitles": {},
                "automatic_captions": {
                    "it": [{"url": "https://yt/api/timedtext?v=1&tlang=it"}],
                    "en": [{"url": "https://yt/api/timedtext?v=1"}],
                },
            }
        )

        with self.assertRaisesRegex(SystemExit, "Rerun with --sub-lang en"):
            download_subtitles(
                "https://example.com/video", Path("/tmp/subtitles"), "it"
            )

        ydl.process_ie_result.assert_not_called()


if __name__ == "__main__":
    unittest.main()
