import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add repository root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


class TestPipeline(unittest.TestCase):

    @patch("google.auth.transport.requests.Request")
    @patch("main.Credentials")
    def test_youtube_preflight_fail(self, mock_credentials_cls, mock_request_cls):
        """
        Test 1: Verify YouTube Auth Pre-flight Check fails fast on invalid_grant.
        Mocks google.oauth2.credentials to simulate an expired token / invalid_grant
        and asserts that verify_youtube_auth raises an explicit AuthError.
        """
        from main import AuthError, verify_youtube_auth

        mock_creds_instance = MagicMock()
        # Simulate invalid_grant error when refreshing token
        mock_creds_instance.refresh.side_effect = Exception("invalid_grant: Token expired or revoked")
        mock_credentials_cls.return_value = mock_creds_instance

        with self.assertRaises(AuthError) as context:
            verify_youtube_auth(
                client_id="dummy_id",
                client_secret="dummy_secret",
                refresh_token="invalid_token"
            )

        self.assertIn("invalid_grant", str(context.exception))
        print("SUCCESS: Test 1 Passed: test_youtube_preflight_fail correctly caught invalid_grant and raised AuthError.")

    @patch("subprocess.run")
    def test_ffmpeg_concat_logic(self, mock_subprocess_run):
        """
        Test 2: Verify long-form chunked rendering generates a properly formatted segments.txt
        and executes the correct 'ffmpeg -f concat -safe 0 -i segments.txt -c copy' command.
        """
        from main import render_long_form_segments_and_concat

        # Dummy segment objects
        segments = [
            {"topic": "Topic A", "script": "Script A", "visual_keywords": ["kw1"]},
            {"topic": "Topic B", "script": "Script B", "visual_keywords": ["kw2"]}
        ]
        
        # Mock assemble_video to create dummy segment files
        def mock_assemble(*args, **kwargs):
            out_path = kwargs.get("output_path", "dummy_segment.mp4")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write("mock_mp4_content")
            return out_path

        mock_subprocess_run.return_value = MagicMock(returncode=0)

        output_path = "test_longform_output.mp4"
        segments_txt_path = "segments.txt"

        with patch("main.generate_audio_and_subtitles", return_value=("dummy.wav", [((0, 1), "TEST")], "voice")), \
             patch("main.download_pexels_videos", return_value=["video.mp4"]), \
             patch("main.assemble_video", side_effect=mock_assemble):

            try:
                render_long_form_segments_and_concat(
                    segments=segments,
                    category="space",
                    pexels_key="dummy_key",
                    config=MagicMock(is_short=False, resolution=(1920, 1080)),
                    output_path=output_path
                )

                # Verify segments.txt file creation & content formatting
                self.assertTrue(os.path.exists(segments_txt_path), "segments.txt was not created!")
                with open(segments_txt_path, "r", encoding="utf-8") as f:
                    content = f.read()

                self.assertIn("file 'segment_0.mp4'", content)
                self.assertIn("file 'segment_1.mp4'", content)

                # Verify FFmpeg stream copy invocation
                mock_subprocess_run.assert_called()
                ffmpeg_cmd = mock_subprocess_run.call_args[0][0]
                self.assertIn("ffmpeg", ffmpeg_cmd[0])
                self.assertIn("concat", ffmpeg_cmd)
                self.assertIn("-safe", ffmpeg_cmd)
                self.assertIn("0", ffmpeg_cmd)
                self.assertIn("-i", ffmpeg_cmd)
                self.assertIn("segments.txt", ffmpeg_cmd)
                self.assertIn("-c", ffmpeg_cmd)
                self.assertIn("copy", ffmpeg_cmd)

                print("SUCCESS: Test 2 Passed: test_ffmpeg_concat_logic successfully verified segments.txt formatting and FFmpeg stream copy command.")
            finally:
                # Cleanup test files
                for f in ["segment_0.mp4", "segment_1.mp4", "segments.txt", output_path, "dummy.wav"]:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except Exception:
                            pass

    def test_top_level_comment_posting(self):
        """
        Test 3: Verify post_top_level_engagement_comment generates a question via Gemini
        and invokes youtube.commentThreads().insert with part='snippet' and body format.
        """
        from main import post_top_level_engagement_comment

        mock_youtube = MagicMock()
        mock_insert = MagicMock()
        mock_youtube.commentThreads().insert.return_value = mock_insert
        mock_insert.execute.return_value = {"id": "comment_12345"}

        mock_client = MagicMock()

        with patch("main.gemini_generate_with_retry", return_value=MagicMock(text="What is the most mysterious phenomenon in the universe?")):
            comment_id = post_top_level_engagement_comment(
                youtube=mock_youtube,
                video_id="video_abc123",
                winning_script_text="In the deep void of space...",
                client=mock_client
            )

        self.assertEqual(comment_id, "comment_12345")
        mock_youtube.commentThreads().insert.assert_called_once()
        kwargs = mock_youtube.commentThreads().insert.call_args[1]
        self.assertEqual(kwargs.get("part"), "snippet")
        self.assertEqual(kwargs["body"]["snippet"]["videoId"], "video_abc123")
        self.assertIn("snippet", kwargs["body"]["snippet"]["topLevelComment"])
        self.assertEqual(kwargs["body"]["snippet"]["topLevelComment"]["snippet"]["textOriginal"], "What is the most mysterious phenomenon in the universe?")
        print("SUCCESS: Test 3 Passed: test_top_level_comment_posting correctly inserted topLevelComment via YouTube Data API.")


if __name__ == "__main__":
    unittest.main()
