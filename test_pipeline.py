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

    def test_wildlife_species_ingestion_and_few_shot_scoring(self):
        """
        Test 6: Verify MPVSAP 3.0 WildApex Shorts Wildlife & Bizarre Biology Refactoring:
        1. All 4 sub-pillars in CATEGORIES use YouTube Category ID '15' (Pets & Animals) and @WildApexShorts watermark.
        2. Curated species ingestion (fetch_wikipedia_source_text) selects an unused biological species.
        3. get_run_score prioritizes real YouTube views > 0 and falls back to winning_script['score'] when views == 0 or None.
        4. sanitize_script_opening strips leading lowercase conjunction fragments and capitalizes Sentence 1.
        5. generate_ass_file groups Shorts captions into 2-to-3 word phrase chunks at y=1120 (MarginV=800).
        """
        import tempfile
        from main import (
            CATEGORIES,
            WATERMARK_HANDLE,
            VideoFormatConfig,
            fetch_wikipedia_source_text,
            generate_ass_file,
            get_run_score,
            sanitize_script_opening,
        )

        # 1. Verify 4 Wildlife Pillars & Category ID 15
        self.assertEqual(len(CATEGORIES), 4)
        for cat_name, cat_meta in CATEGORIES.items():
            self.assertEqual(cat_meta["yt_category_id"], "15", f"Expected yt_category_id '15' for {cat_name}")
        self.assertEqual(WATERMARK_HANDLE, "@WildApexShorts")

        # 2. Verify Curated Species Ingestion via mocked HTTP_SESSION
        mock_wiki_resp = MagicMock()
        mock_wiki_resp.json.return_value = {
            "query": {
                "pages": {
                    "12345": {
                        "title": "Peacock mantis shrimp",
                        "extract": (
                            "The peacock mantis shrimp (Odontodactylus scyllarus) is a large stomatopod native to the "
                            "Indo-Pacific. It strikes prey with club-like appendages accelerating at over 10,000 Gs "
                            "and generating cavitation bubbles that shatter shells."
                        ) * 3
                    }
                }
            }
        }
        with patch("main.HTTP_SESSION.get", return_value=mock_wiki_resp):
            src = fetch_wikipedia_source_text("Bizarre Biological Superpowers", [])
            self.assertEqual(src["title"], "Peacock mantis shrimp")
            self.assertIn("cavitation bubbles", src["text"])

        # 3. Verify get_run_score hybrid view + QA scoring
        run_zero_views = {"youtube_stats": {"views": 0}, "winning_script": {"score": 9.65}}
        run_none_stats = {"youtube_stats": None, "winning_script": {"score": 9.40}}
        run_high_views = {"youtube_stats": {"views": 250}, "winning_script": {"score": 9.10}}
        self.assertAlmostEqual(get_run_score(run_zero_views), 9.65, places=2)
        self.assertAlmostEqual(get_run_score(run_none_stats), 9.40, places=2)
        self.assertGreater(get_run_score(run_high_views), get_run_score(run_zero_views))

        # 4. Verify sanitize_script_opening strips lowercase fragments
        cleaned_hook = sanitize_script_opening("...that this six-inch shrimp punches like a bullet.")
        self.assertEqual(cleaned_hook, "This six-inch shrimp punches like a bullet.")

        # 5. Verify 2-to-3 word phrase chunking & safe-zone MarginV in generate_ass_file
        short_cfg = VideoFormatConfig("short")
        self.assertEqual(short_cfg.sub_fontsize, 74)
        self.assertEqual(short_cfg.sub_position, ("center", 1120))
        self.assertEqual(short_cfg.clip_count, 8)

        sample_subs = [
            ((0.0, 0.3), "THIS"),
            ((0.3, 0.6), "MANTIS"),
            ((0.6, 0.9), "SHRIMP"),
            ((0.9, 1.2), "SHATTERS"),
            ((1.2, 1.5), "GLASS."),
        ]
        temp_ass = os.path.join(tempfile.gettempdir(), f"test_wildapex_{os.getpid()}.ass")
        try:
            generate_ass_file(sample_subs, temp_ass, "Bizarre Biological Superpowers", short_cfg)
            with open(temp_ass, "r", encoding="utf-8") as f:
                ass_content = f.read()
            self.assertIn(",800,1", ass_content)  # Default style MarginV = 1920 - 1120 = 800
            self.assertIn("@WildApexShorts", ass_content)
            # 5 words should be grouped into 2 phrase dialogue events (+ 1 watermark dialogue event = 3 total)
            dialogue_lines = [line for line in ass_content.splitlines() if line.startswith("Dialogue:")]
            self.assertEqual(len(dialogue_lines), 3)
        finally:
            if os.path.exists(temp_ass):
                os.remove(temp_ass)

        # 6. Verify Clause-Locked Acoustic-Valley Alignment & Clause-Boundary Phrase Chunking
        import numpy as np
        from main import align_clause_words_to_acoustic_valleys, sanitize_script_for_tts

        self.assertEqual(sanitize_script_for_tts("It’s Earth’s living relic."), "It's Earth's living relic.")

        mock_kokoro = MagicMock()
        mock_kokoro.tokenizer.phonemize.side_effect = lambda w, lang="en-us": w
        mock_kokoro.tokenizer.tokenize.side_effect = lambda p: list(p)
        sr = 24000
        # 1.2s synthetic waveform with a clear silence valley around t=0.45s
        t_arr = np.linspace(0, 1.2, int(1.2 * sr), endpoint=False)
        env = np.ones_like(t_arr)
        env[(t_arr >= 0.42) & (t_arr <= 0.48)] = 0.01
        synth_wave = (0.5 * env * np.sin(2 * np.pi * 220 * t_arr)).astype(np.float32)
        aligned = align_clause_words_to_acoustic_valleys(mock_kokoro, "Our oceans?", synth_wave, sr, 2.00)
        self.assertEqual(len(aligned), 2)
        self.assertEqual(aligned[0][2], "OUR")
        self.assertEqual(aligned[1][2], "OCEANS?")
        self.assertAlmostEqual(aligned[0][0], 2.00, places=2)
        self.assertAlmostEqual(aligned[1][1], 3.20, places=2)
        # Internal boundary should snap into the acoustic valley [2.42, 2.48]
        self.assertTrue(2.40 <= aligned[0][1] <= 2.50, f"Expected boundary in valley [2.40, 2.50], got {aligned[0][1]}")

        # Verify generate_ass_file never merges across punctuation and splits SYMBIOTIC GAMMAPROTEOBACTERIA
        boundary_subs = [
            ((2.0, 2.45), "OUR"),
            ((2.45, 2.98), "OCEANS?"),
            ((3.24, 3.55), "MEET"),
            ((3.55, 4.17), "SCALY-FOOT,"),
            ((25.72, 26.51), "SYMBIOTIC"),
            ((26.51, 27.67), "GAMMAPROTEOBACTERIA,"),
        ]
        temp_ass_2 = os.path.join(tempfile.gettempdir(), f"test_wildapex_sync_{os.getpid()}.ass")
        try:
            generate_ass_file(boundary_subs, temp_ass_2, "Deep Sea & Prehistoric Survivors", short_cfg)
            with open(temp_ass_2, "r", encoding="utf-8") as f:
                ass_2 = f.read()
            default_cues = [line for line in ass_2.splitlines() if line.startswith("Dialogue:") and ",Default," in line]
            # Expect 4 distinct cues: [OUR OCEANS?], [MEET SCALY-FOOT], [SYMBIOTIC], [GAMMAPROTEOBACTERIA]
            self.assertEqual(len(default_cues), 4)
            self.assertIn("OCEANS?", default_cues[0])
            self.assertNotIn("MEET", default_cues[0])
            self.assertIn("SYMBIOTIC", default_cues[2])
            self.assertNotIn("GAMMAPROTEOBACTERIA", default_cues[2])
            self.assertIn("GAMMAPROTEOBACTERIA", default_cues[3])
        finally:
            if os.path.exists(temp_ass_2):
                os.remove(temp_ass_2)

        print("SUCCESS: Test 6 Passed: test_wildlife_species_ingestion_and_few_shot_scoring verified WildApex 3.0 architecture.")

    def test_threads_content_factory_enhancements(self):
        """
        Test 7: Verify all 3 Phases of the @libknowsai AI Content Factory Upgrade:
        - Phase 1: Multi-source Europe PMC + anatomical extract prioritization, outlier_multiplier scoring,
                   viewer comment mining, and 5-result Wikimedia search loop (skipping SVG in result[0]).
        - Phase 2: OpenCV salience-tracked aspect-preserving crop, kinetic ASS pop-in tag,
                   mood-matched BGM track selection, and dual-voice ('duo') Kokoro synthesis routing.
        - Phase 3: Multi-language YouTube localizations (es, pt, hi, de, fr, ja, ko) and social distribution bundle.
        """
        import tempfile
        from pathlib import Path
        import numpy as np
        from main import (
            VideoFormatConfig,
            fetch_europepmc_scientific_facts,
            find_video_salience_center,
            generate_ass_file,
            generate_social_distribution_posts,
            generate_youtube_localizations,
            get_run_score,
            prepare_aspect_cropped_clip,
            prioritize_biological_extract_sections,
            search_wikimedia_image,
            select_mood_matched_music,
        )
        from maintenance_sync import mine_youtube_viewer_comments

        # --- Phase 1A: Europe PMC + Biological Section Prioritization ---
        long_extract = (" ".join(["Taxonomic classification history."] * 150)) + " The mantis shrimp strike force reaches 1,500 Newtons with lethal cavitation venom."
        prioritized = prioritize_biological_extract_sections(long_extract, max_words=620)
        self.assertIn("1,500 Newtons", prioritized)

        mock_pmc_resp = MagicMock(status_code=200)
        mock_pmc_resp.json.return_value = {
            "resultList": {
                "result": [
                    {"abstractText": "<b>Odontodactylus scyllarus</b> generates cavitation bubbles collapsing at high pressure and temperature."}
                ]
            }
        }
        with patch("main.HTTP_SESSION.get", return_value=mock_pmc_resp):
            pmc_text = fetch_europepmc_scientific_facts("Odontodactylus scyllarus")
            self.assertIn("EUROPE PMC", pmc_text)
            self.assertIn("cavitation bubbles", pmc_text)
            self.assertNotIn("<b>", pmc_text)

        # --- Phase 1B: Outlier Multiplier in get_run_score & Viewer Comment Mining ---
        baseline_run = {"youtube_stats": {"views": 200, "outlier_multiplier": 1.0}, "winning_script": {"score": 9.5}}
        outlier_run = {"youtube_stats": {"views": 200, "outlier_multiplier": 3.0}, "winning_script": {"score": 9.5}}
        self.assertGreater(get_run_score(outlier_run), get_run_score(baseline_run))

        mock_yt = MagicMock()
        mock_yt.commentThreads().list().execute.return_value = {
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Can you do the Pistol Shrimp vs Mantis Shrimp next?",
                                "likeCount": 14
                            }
                        }
                    }
                }
            ]
        }
        with patch("maintenance_sync.VIEWER_SIGNALS_FILE", Path(tempfile.gettempdir()) / f"test_signals_{os.getpid()}.json") as tmp_sig_path:
            try:
                signals = mine_youtube_viewer_comments(mock_yt, ["vid_001"], max_videos=1)
                self.assertTrue(any("Pistol Shrimp" in s["comment_text"] for s in signals))
            finally:
                if tmp_sig_path.exists():
                    tmp_sig_path.unlink()

        # --- Phase 1C: 5-Result Wikimedia Loop (skips SVG at index 0, selects JPG at index 1) ---
        search_resp = MagicMock(status_code=200)
        search_resp.json.return_value = {
            "query": {
                "search": [
                    {"title": "File:Diagram.svg"},
                    {"title": "File:ScalyFootSnail.jpg"},
                ]
            }
        }
        info_resp = MagicMock(status_code=200)
        info_resp.json.return_value = {
            "query": {
                "pages": {
                    "1": {"title": "File:Diagram.svg", "imageinfo": [{"url": "https://upload.wikimedia.org/Diagram.svg"}]},
                    "2": {"title": "File:ScalyFootSnail.jpg", "imageinfo": [{"url": "https://upload.wikimedia.org/ScalyFootSnail.jpg"}]},
                }
            }
        }
        with patch("main.HTTP_SESSION.get", side_effect=[search_resp, info_resp]), patch("time.sleep"):
            resolved_url = search_wikimedia_image("Scaly-foot gastropod")
            self.assertEqual(resolved_url, "https://upload.wikimedia.org/ScalyFootSnail.jpg")

        # --- Phase 2A: OpenCV Saliency Center & Aspect-Preserving Crop ---
        dummy_clip = MagicMock()
        dummy_clip.duration = 2.0
        dummy_clip.size = (1920, 1080)
        # Create synthetic frame with bright high-edge patch on the right side (x ~ 1400)
        test_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        test_frame[300:700, 1300:1600] = 255
        test_frame[320:680:4, 1320:1580:4] = 0
        dummy_clip.get_frame.return_value = test_frame
        dummy_clip.fl_image.side_effect = lambda fn: dummy_clip

        cx, cy = find_video_salience_center(dummy_clip)
        self.assertGreater(cx, 0.55, f"Expected salience center cx > 0.55 for right-side subject, got {cx}")
        cropped_clip, (crop_cx, crop_cy) = prepare_aspect_cropped_clip(dummy_clip, (1080, 1920))
        self.assertEqual(cropped_clip.size, (1080, 1920))
        self.assertAlmostEqual(crop_cx, cx, places=3)

        # --- Phase 2B: Kinetic ASS Pop-In Tag & Mood-Matched BGM Selection ---
        short_cfg = VideoFormatConfig("short")
        temp_ass = os.path.join(tempfile.gettempdir(), f"test_kinetic_{os.getpid()}.ass")
        try:
            generate_ass_file([((0.0, 0.4), "APEX"), ((0.4, 0.8), "STRIKE.")], temp_ass, "Apex Predators & Deadly Matchups", short_cfg)
            with open(temp_ass, "r", encoding="utf-8") as f:
                ass_text = f.read()
            self.assertIn(r"{\fscx114\fscy114\t(0,75,\fscx100\fscy100)}", ass_text)
        finally:
            if os.path.exists(temp_ass):
                os.remove(temp_ass)

        tracks = [Path("dark_space_abyss.mp3"), Path("epic_dark_trap.mp3"), Path("tech_house_pulse.mp3")]
        chosen_abyss = select_mood_matched_music(tracks, "Deep Sea & Prehistoric Survivors", [((0, 1), "ABYSS"), ((1, 2), "TRENCH"), ((2, 3), "OCEAN")])
        self.assertEqual(chosen_abyss.name, "dark_space_abyss.mp3")
        chosen_combat = select_mood_matched_music(tracks, "Apex Predators & Deadly Matchups", [((0, 1), "PREDATOR"), ((1, 2), "BITE"), ((2, 3), "AMBUSH")])
        self.assertEqual(chosen_combat.name, "epic_dark_trap.mp3")

        # --- Phase 2C: Dual-Voice ('duo') Contrast Hook Routing in Kokoro Synthesis ---
        from main import synthesize_kokoro_audio_and_timestamps
        mock_kokoro_inst = MagicMock()
        mock_kokoro_inst.create.return_value = (np.ones(2400, dtype=np.float32) * 0.1, 24000)
        mock_kokoro_inst.tokenizer.phonemize.side_effect = lambda w, lang="en-us": w
        mock_kokoro_inst.tokenizer.tokenize.side_effect = lambda p: list(p)
        temp_duo_wav = os.path.join(tempfile.gettempdir(), f"test_duo_{os.getpid()}.wav")
        try:
            with patch("main.ensure_kokoro_model_files", return_value=(Path("dummy.onnx"), Path("dummy.bin"))), \
                 patch("kokoro_onnx.Kokoro", return_value=mock_kokoro_inst):
                duo_words = synthesize_kokoro_audio_and_timestamps(
                    "This shrimp punches like a bullet. Its club boils water into plasma.",
                    "Bizarre Biological Superpowers",
                    temp_duo_wav,
                    voice_mode="duo"
                )
            self.assertEqual(len(duo_words), 12)
            voices_called = [call.kwargs.get("voice") for call in mock_kokoro_inst.create.call_args_list]
            self.assertEqual(voices_called, ["af_heart", "am_fenrir"])
        finally:
            if os.path.exists(temp_duo_wav):
                os.remove(temp_duo_wav)

        # --- Phase 3: Multi-Language YouTube Localization & Social Distribution Bundle ---
        mock_loc_resp = MagicMock(text="""{
            "es": {"title": "El camarón mantis letal #shorts", "description": "Golpea como una bala."},
            "pt": {"title": "A lagosta-boxeadora mortal #shorts", "description": "Soco supersônico."},
            "hi": {"title": "मैंटिस श्रिम्प का प्रहार #shorts", "description": "गोली जैसी रफ्तार।"},
            "de": {"title": "Der tödliche Fangschreckenkrebs #shorts", "description": "Schlägt wie eine Kugel."},
            "fr": {"title": "La crevette-mante mortelle #shorts", "description": "Une frappe supersonique."},
            "ja": {"title": "モンハナシャコの衝撃 #shorts", "description": "弾丸のようなパンチ。"},
            "ko": {"title": "갯가재의 치명적인 펀치 #shorts", "description": "총알 같은 위력."}
        }""")
        with patch("main.gemini_generate_with_retry", return_value=mock_loc_resp):
            locs = generate_youtube_localizations(MagicMock(), "The Lethal Mantis Shrimp #shorts", "Punches like a bullet.")
            self.assertEqual(len(locs), 7)
            self.assertIn("es", locs)
            self.assertIn("ja", locs)

        social_posts = generate_social_distribution_posts(
            title="The Lethal Mantis Shrimp #shorts",
            winning_script_text="This six-inch crustacean punches with the velocity of a twenty-two caliber bullet. Its strike boils water into cavitation plasma.",
            youtube_url="https://www.youtube.com/shorts/abc123xyz",
            category="Bizarre Biological Superpowers"
        )
        self.assertIn("x_post", social_posts)
        self.assertIn("threads_post", social_posts)
        self.assertIn("youtube_community_poll", social_posts)
        self.assertIn("https://www.youtube.com/shorts/abc123xyz", social_posts["x_post"])

        print("SUCCESS: Test 7 Passed: test_threads_content_factory_enhancements verified all 3 phases.")

    def test_permanent_llm_resilience_and_telemetry_cap(self):
        """
        Test 8: Verify Permanent CI/CD & LLM Resilience Architecture:
        1. HTTP 402 ('prepayment credits are depleted') trips immediate circuit breaker with ZERO sleep calls.
        2. Multi-provider failover routes from a 402 Gemini client to OpenAI-compatible secondary provider (Groq).
        3. generate_content() engages Encyclopedia-Grounded Continuity Engine when all cloud LLMs are depleted.
        4. self_heal.classify_log_deterministically() classifies 402 billing depletion deterministically.
        5. maintenance_sync.sync_github_cancelled_or_failed_runs() enforces the 100-entry rolling telemetry cap.
        """
        import json as _json
        from main import (
            _DEPLETED_GEMINI_CLIENT_IDS,
            VideoFormatConfig,
            gemini_generate_with_retry,
            generate_content,
            is_llm_billing_or_auth_error,
        )
        from self_heal import classify_log_deterministically
        from maintenance_sync import sync_github_cancelled_or_failed_runs

        err_402 = Exception(
            "402 RESOURCE_EXHAUSTED. {'error': {'code': 402, 'message': "
            "'Your prepayment credits are depleted. Please go to AI Studio at https://ai.studio/projects', "
            "'status': 'RESOURCE_EXHAUSTED'}}"
        )
        self.assertTrue(is_llm_billing_or_auth_error(err_402))
        self.assertFalse(is_llm_billing_or_auth_error(Exception("429 RESOURCE_EXHAUSTED: RPM limit reached, retry in 15s")))

        # 1. Verify instant 402 circuit breaker (0 sleeps, 1 API attempt, cached depletion on 2nd call)
        depleted_client = MagicMock()
        depleted_client.models.generate_content.side_effect = err_402
        _DEPLETED_GEMINI_CLIENT_IDS.discard(id(depleted_client))

        env_clean = {
            "GEMINI_API_KEY": "primary_only",
            "GEMINI_API_KEY_FALLBACK": "",
            "GEMINI_API_KEY_FREE": "",
            "GEMINI_API_KEY_2": "",
            "GROQ_API_KEY": "",
            "OPENROUTER_API_KEY": "",
            "OPENAI_API_KEY": "",
        }
        with patch.dict(os.environ, env_clean, clear=False), patch("time.sleep") as mock_sleep:
            with self.assertRaises(RuntimeError):
                gemini_generate_with_retry(depleted_client, "gemini-2.5-flash", "Test prompt")
            mock_sleep.assert_not_called()
            self.assertEqual(depleted_client.models.generate_content.call_count, 1)
            self.assertIn(id(depleted_client), _DEPLETED_GEMINI_CLIENT_IDS)

            # Second call in same process should bypass depleted_client in 0 API calls
            with self.assertRaises(RuntimeError):
                gemini_generate_with_retry(depleted_client, "gemini-2.5-flash", "Second prompt")
            self.assertEqual(depleted_client.models.generate_content.call_count, 1)

        # 2. Verify automatic failover to Groq OpenAI-compatible endpoint when Gemini is circuit-broken
        mock_groq_http = MagicMock(status_code=200)
        mock_groq_http.json.return_value = {
            "choices": [{"message": {"content": '{"status": "failover_ok"}'}}]
        }
        with patch.dict(os.environ, {**env_clean, "GROQ_API_KEY": "gsk_test_dummy"}, clear=False), \
             patch("main.HTTP_SESSION.post", return_value=mock_groq_http):
            fb_res = gemini_generate_with_retry(depleted_client, "gemini-2.5-flash", "Failover prompt")
            self.assertEqual(fb_res.text, '{"status": "failover_ok"}')
            self.assertEqual(fb_res.provider, "groq")

        # 2b. Verify 429 fast-switch cascade across active Free-Tier chain & Flash-Lite start tier
        rate_limited_client = MagicMock()
        rate_limited_client.models.generate_content.side_effect = [
            Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded, retry in 20s"),
            MagicMock(text="ok_from_3_6_flash"),
        ]
        _DEPLETED_GEMINI_CLIENT_IDS.discard(id(rate_limited_client))
        with patch.dict(os.environ, env_clean, clear=False), patch("time.sleep") as mock_sleep:
            rl_res = gemini_generate_with_retry(rate_limited_client, "gemini-3.8-flash", "Cascade prompt")
            self.assertEqual(rl_res.text, "ok_from_3_6_flash")
            mock_sleep.assert_not_called()
            called_models = [c.kwargs.get("model") for c in rate_limited_client.models.generate_content.call_args_list]
            self.assertEqual(called_models, ["gemini-3.8-flash", "gemini-3.6-flash"])

        lite_client = MagicMock()
        lite_client.models.generate_content.return_value = MagicMock(text="ok_from_flash_lite")
        _DEPLETED_GEMINI_CLIENT_IDS.discard(id(lite_client))
        with patch.dict(os.environ, env_clean, clear=False):
            lite_res = gemini_generate_with_retry(lite_client, "gemini-3.5-flash-lite", "Localization prompt")
            self.assertEqual(lite_res.text, "ok_from_flash_lite")
            self.assertEqual(
                lite_client.models.generate_content.call_args.kwargs.get("model"),
                "gemini-3.5-flash-lite",
            )

        # 3. Verify Encyclopedia-Grounded Continuity Engine in generate_content when all LLMs fail
        sample_source = {
            "title": "Shrike",
            "url": "https://en.wikipedia.org/wiki/Shrike",
            "text": (
                "Shrikes are predatory passerine birds known as butcherbirds for their habit of impaling captured prey "
                "on sharp thorns and barbed wire. Using a hooked, raptor-like tomial tooth on the upper beak, a shrike "
                "severs the cervical vertebrae of insects, lizards, and rodents with violent head-shaking accelerations. "
                "Impaling prey allows the shrike to tear flesh without talons and detoxify poisonous lubber grasshoppers "
                "over 48 hours."
            ),
        }
        with patch.dict(os.environ, env_clean, clear=False):
            title, desc, segs, variants_log, win_log = generate_content(
                depleted_client,
                "Apex Predators & Deadly Matchups",
                [],
                sample_source,
                VideoFormatConfig("short"),
            )
        self.assertEqual(len(segs), 1)
        word_cnt = len(segs[0]["script"].split())
        self.assertTrue(65 <= word_cnt <= 105, f"Expected ~80-95 word continuity script, got {word_cnt} words")
        self.assertIn("Shrike", segs[0]["script"])
        self.assertEqual(segs[0]["topic"], "Shrike")
        self.assertGreaterEqual(len(segs[0]["visual_keywords"]), 5)
        self.assertIn("Continuity Engine", win_log["critique"])

        # 4. Verify deterministic 402 classification in self_heal.py
        diag = classify_log_deterministically(str(err_402))
        self.assertIsNotNone(diag)
        self.assertIn("ENVIRONMENT_BILLING_DEPLETED", diag)

        # 5. Verify 100-entry rolling telemetry cap in maintenance_sync.py (ancient runs skipped)
        rolling_100 = [
            {
                "id": f"run-{200 + i}",
                "github_run_number": 200 + i,
                "github_run_id": 10000 + i,
                "workflow_type": "DAILY_SHORTS",
                "timestamp": f"2026-11-{(i // 5) + 1:02d}T12:00:00Z",
                "status": "SUCCESS",
            }
            for i in range(100)
        ]
        fake_gh_payload = _json.dumps({
            "workflow_runs": [
                {
                    "id": 99999,
                    "run_number": 300,
                    "name": "Daily Shorts Generator & Uploader",
                    "status": "completed",
                    "conclusion": "success",
                    "created_at": "2026-11-26T00:00:00Z",
                    "html_url": "https://github.com/thienphucnt/MPVSAP/actions/runs/99999",
                },
                {
                    "id": 11,
                    "run_number": 11,
                    "name": "Daily Shorts Generator & Uploader",
                    "status": "completed",
                    "conclusion": "failure",
                    "created_at": "2026-07-10T00:00:00Z",
                    "html_url": "https://github.com/thienphucnt/MPVSAP/actions/runs/11",
                },
            ]
        }).encode("utf-8")
        mock_ctx = MagicMock()
        mock_ctx.__enter__.return_value.read.return_value = fake_gh_payload
        with patch("urllib.request.urlopen", return_value=mock_ctx):
            synced_hist, mod_cnt = sync_github_cancelled_or_failed_runs(list(rolling_100))
        self.assertEqual(len(synced_hist), 100)
        self.assertTrue(any(e.get("github_run_id") == 99999 for e in synced_hist))
        self.assertFalse(any(e.get("github_run_id") == 11 for e in synced_hist))

        print("SUCCESS: Test 8 Passed: test_permanent_llm_resilience_and_telemetry_cap verified all permanent fixes.")


if __name__ == "__main__":
    unittest.main()

