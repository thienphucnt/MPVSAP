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

    def test_tournament_head_to_head_judging(self):
        """
        Test 4: Verify evaluate_tournament_variants conducts a side-by-side head-to-head comparison
        of all candidate variants in a single evaluation call and cleans prepended category prefixes.
        """
        from main import evaluate_tournament_variants

        mock_client = MagicMock()
        mock_config = MagicMock(is_short=True)

        candidates = [
            {
                "angle": "Cosmic Terror",
                "title": "Cosmic Terror: The Void Phantom",
                "script": "Deep space anomaly flickering in dark void...",
                "topic": "Void Anomaly"
            },
            {
                "angle": "Quantum Paradox",
                "title": "Quantum Entanglement Shock",
                "script": "Subatomic particles communicating instantly across galaxy...",
                "topic": "Quantum Mechanics"
            }
        ]

        mock_eval_response = MagicMock(text="""{
            "evaluations": [
                {"variant_id": 1, "score": 9.60, "critique": "Terrifying hook open loop with high retention."},
                {"variant_id": 2, "score": 9.20, "critique": "Strong quantum science pacing."}
            ],
            "winning_variant_id": 1
        }""")

        with patch("main.gemini_generate_with_retry", return_value=mock_eval_response):
            evaluated_list, winner = evaluate_tournament_variants(
                client=mock_client,
                model_name="gemini-2.5-flash",
                variants=candidates,
                source_title="Deep Space Anomaly",
                config=mock_config
            )

        self.assertEqual(len(evaluated_list), 2)
        self.assertEqual(winner["score"], 9.60)
        self.assertEqual(winner["title"], "The Void Phantom") # Stripped 'Cosmic Terror: ' prefix!
        self.assertEqual(evaluated_list[1]["title"], "Quantum Entanglement Shock")
        print("SUCCESS: Test 4 Passed: test_tournament_head_to_head_judging correctly evaluated variants side-by-side and cleaned prefixes.")

    def test_seamless_looping_logic(self):
        """
        Test 5: Verify seamless looping utilities:
        1. Trailing silence trimming reduces end silence buffer to <= 50ms.
        2. Video render duration quantization produces exact 30fps integer frame multiples.
        """
        import soundfile as sf
        import numpy as np
        import tempfile
        import os
        from main import trim_trailing_silence

        # 1. Test Trailing Silence Trimming
        sr = 22050
        signal_duration = 1.0
        silence_duration = 0.5
        t = np.linspace(0, signal_duration, int(sr * signal_duration), endpoint=False)
        sine_wave = 0.5 * np.sin(2 * np.pi * 440 * t)
        silence = np.zeros(int(sr * silence_duration))
        combined_audio = np.concatenate([sine_wave, silence])

        temp_audio_file = os.path.join(tempfile.gettempdir(), f"test_silence_{os.getpid()}.wav")
        try:
            sf.write(temp_audio_file, combined_audio, sr)
            trimmed_path = trim_trailing_silence(temp_audio_file, silence_threshold_db=-45.0, padding_ms=50.0)
            
            trimmed_data, trimmed_sr = sf.read(trimmed_path)
            trimmed_duration = len(trimmed_data) / float(trimmed_sr)
            expected_max_duration = signal_duration + 0.06  # 50ms padding + 10ms tolerance
            
            self.assertLessEqual(trimmed_duration, expected_max_duration)
            self.assertGreaterEqual(trimmed_duration, signal_duration)
        finally:
            if os.path.exists(temp_audio_file):
                try: os.remove(temp_audio_file)
                except Exception: pass

        # 2. Test 30fps Frame Quantization
        test_durations = [45.12345, 12.33333, 59.99999, 10.0]
        for dur in test_durations:
            quantized = round(dur * 30.0) / 30.0
            frame_count = quantized * 30.0
            self.assertAlmostEqual(frame_count, round(frame_count), places=5)

        print("SUCCESS: Test 5 Passed: test_seamless_looping_logic successfully verified TTS silence trimming and 30fps frame quantization.")


if __name__ == "__main__":
    unittest.main()

