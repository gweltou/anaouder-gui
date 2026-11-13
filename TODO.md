# TODO

Single list of pending work for Anaouder: packaging chores, features, bugs and `TODO`/`XXX` comments found in the code.
It merges `docs/TODO.txt` (old, French, partly outdated) and the comments in `src/`.
Last audit: 2026-11-13 (re-checked against a full read of the largest source files; see #49-#58, #67-#69).

## How to use this file

- Every task has a **stable number** (`#12`). Refer to it in commits, issues and chat ("fix #12"). Never renumber; new tasks get the next free number.
- **Status marker**: `[ ]` not done · `[~]` doing · `[x]` done.
  Change it when you start or finish a task. Don't delete finished tasks; move them to "Done / stale" at the bottom.
- **Severity**: `S1` crash / data loss · `S2` broken feature or wrong result · `S3` annoyance or missing small feature · `S4` cleanup / nice to have.
- **Validity** (result of the audit against the current code):
  `valid` confirmed in code · `unverified` plausible but needs a repro before work starts · `stale` no longer applies (kept for history).
- `Where` gives a file (and line at audit time; lines drift, search for the quoted text).
- When you resolve a `TODO` comment in the code, remove the comment and tick the task here.
- Agents: read this file before starting non-trivial work, pick tasks from it, and update the markers.

---

## 1. Packaging / repo structure

- [ ] **#1 · S2 · valid — Rename the `src` package to `anaouder`.**
  Why: with no `[tool.setuptools]` config, `pip install .` installs the contents of `src/` as top-level modules (`utils`, `main`, `settings`, `ui`, `lang`…), which can clash with other packages, and stale `build/lib` files leak into wheels. A package literally called `src` is also fragile.
  Plan:
  1. `git mv src anaouder`; replace `from src.` / `import src.` with `anaouder.` in `main.py`, `anaouder/`, `tests/` (and any `"src.…"` string, e.g. mock patches).
  2. `anaouder.spec`: `hiddenimports` (`src.lang.*` → `anaouder.lang.*`).
  3. `pyproject.toml`: add `[tool.setuptools.packages.find]` with `include = ["anaouder*"]`, and package data if needed.
  4. Delete `build/lib`, `src/anaouder_gui.egg-info/`, reinstall with `pip install -e .`; make sure `build/`, `*.egg-info/` are git-ignored.
  5. Update `CLAUDE.md` (all `src/…` paths and the "Tests import `src.*`" note), `docs/`, `build_macos-x86.sh`, workflows.
  6. Check `main.py` (root) still works, run the tests, run a PyInstaller build.
  Interim option if the rename is postponed: only step 3 with `include = ["src*"]`.
- [ ] **#2 · S4 · valid — `git rm icons/anaouder_splash_ver.png`.** The spec now writes the version splash to PyInstaller's `workpath`; the tracked file is unused (already staged as deleted).
- [ ] **#3 · S4 · valid — Declare missing dependencies in `pyproject.toml`.** `jiwer` (used by `services/aligner.py`) and `numpy` are imported but not declared. Verify with a clean venv.
- [ ] **#4 · S4 · valid — Spec small cleanups** (`anaouder.spec`): `argv_emulation=True` on all platforms, `COLLECT upx=True` vs `EXE upx=USE_UPX`, stale module docstring, manual `hiddenimports`.
- [ ] **#5 · S3 · valid — `test_remove_fillers` fails.** `tests/test_adapt_subtitles.py::test_remove_fillers` gets `\xa0` before `?` instead of a plain space. Decide whether the code or the test is wrong.
- [ ] **#6 · S4 · valid — `building/Windows/anaouder_installer.iss` hardcodes `MyAppVersion "1.1.1"`** (CI overrides it, local builds don't). Keep in sync or drop the default.

## 2. Features

- [ ] **#10 · S3 · valid — Search and replace (Ctrl+F).** `MainWindow.search()` is a stub that prints "search tool" (`src/main.py` ~2399, comment `## Search TODO` ~170). Use a modeless `QDialog`.
- [ ] **#11 · S3 · unverified — Add the `media-source` metadata automatically when saving `.ali`** if not already present. No code references `media-source`; `media-path` is written in `src/file_io/file_manager.py`. Clarify the intended difference between the two before implementing.
- [ ] **#12 · S4 · unverified — Hide the `audio-path` metadata / insert it automatically when opening a media.** `audio-path` is read as a legacy alias and stripped on save (`file_manager.py` ~203-410); the note probably predates `media-path`. Confirm whether `audio-path` is still wanted.
- [~] **#13 · S3 · partly done — Delete a segment only, keeping the text.** Already implemented: `DeleteSegmentsCommand` / `DocumentController.deleteSegments` and the "Delete audio segment" action in the waveform and text context menus. Left: a shortcut (Shift+Del) and a toolbar button (`QAction` `delete_segment` has no shortcut in `src/actions.py`).
- [ ] **#14 · S3 · valid — Add a word to the autocorrect dictionary** (from the spellcheck context menu).
- [ ] **#15 · S3 · valid — Substitution dictionary** (user-defined replacements).
- [ ] **#16 · S4 · unverified — Enable the subtitles margin automatically when a `subtitles` tag is found in the document.** The tag is filtered in `video_widget.py:132` and `file_io/srt.py:45`, nothing enables a margin from it.
- [ ] **#17 · S3 · valid — Enforce the media cache size limit.** The spinbox in `src/ui/parameters_dialog.py:~961` is disabled (`# TODO`), the value is saved under `cache/media_cache_size`, and `cache_system.py` has no eviction. Implement eviction (oldest first), then enable the spinbox.
- [ ] **#18 · S3 · valid — Full-screen mode for the video widget.** No `showFullScreen` anywhere.
- [ ] **#19 · S3 · unverified — CSV export.** Check `src/exports/` first; not listed in CLAUDE.md formats.
- [ ] **#20 · S3 · valid — Whisper support as an alternative ASR backend** (and multilingual Fr/En/Cy models). No reference in code; needs a model-type abstraction (see #21).
- [ ] **#21 · S3 · valid — Model library file with several sources** (URL and local paths). Proposed format (YAML or JSON): `file_version`, and per model `name`, `lang` (comma list or `*`), `type` (`kaldi-vosk`, `whisper-onnx`, `pyannote`), `footprint` (MB RAM), `download_url`, `modelcard`, `desc_<lang>`, `sha256`. Related: `src/services/model_manager.py`, `docs/model_list.json`.
- [ ] **#22 · S4 · valid — Localize `convert_quotation_marks`** to the document language's quotation marks (`src/services/adapt_subtitles.py:~343`).

## 3. Bugs

Bugs from `docs/TODO.txt` have not been re-reproduced unless stated; `unverified` means "check before fixing".

- [ ] **#30 · S2 · unverified — Joining two segments sometimes fails** (`src/commands.py:~135`, `# TODO: fix bug when joining (sometimes)` in `JoinUtterancesCommand.redo`). Needs a repro.
- [ ] **#31 · S2 · unverified — Density colour not refreshed after joining two segments** (probably the commented-out `waveform.refreshSegmentInfo()` in `JoinUtterancesCommand.undo`, `src/commands.py:~137`).
- [ ] **#32 · S2 · valid — Special tokens disappear when a word is replaced in the same block** (`ReplaceTextCommand`, `src/commands.py:~576`). `new_text` should be HTML including formatting and metadata.
- [ ] **#34 · S1 · unverified — Crash on first start on Windows when offline.** Look at model list fetching / `ostilhou` data download at startup.
- [ ] **#35 · S1 · unverified — Segfault in `libswresample` (`QFFmpeg::AudioR…`) when playing 24-bit PCM stereo 48 kHz files** (`pcm_s24le`). Qt Multimedia/FFmpeg issue; consider converting such media on import, or a warning. Also: no transcription with these formats.
- [ ] **#36 · S3 · valid in code — Waveform can be scrolled by wheel beyond its bounds.** `_scroll_view(fast=True)` with `USE_SCROLL_SMOOTHING` false (macOS only, `settings.py`) does `t_left += ...` without calling `_check_for_out_of_view()`.
- [ ] **#37 · S3 · valid in code — When following the playhead, the view can go beyond the waveform bounds.** `updatePlayHead` sets `t_left = position - width*0.5/ppsec` with no clamp (`src/ui/waveform/waveform_widget.py`). Fix #36 and #37 together by clamping in one helper.
- [ ] **#38 · S3 · unverified — Multi-selection on the waveform** needs fixing (description is vague; reproduce and rewrite this entry).
- [ ] **#39 · S3 · unverified — Warn when the file given by `audio-path`/`media-path` doesn't exist.** `file_manager.py:~135` already calls `showError` in one path; check the others.
- [ ] **#40 · S3 · unverified — "Recognize" on several selected segments transcribes in reverse order.** Suspect: `MainWindow.transcribeAction` iterates `waveform.active_segments` in selection order; sort by start time.
- [ ] **#41 · S3 · unverified — First save: the system dialog's file name is empty** (`src/main.py:~1569`, `# TODO: When saving, the folder and basename are not set`).
- [ ] **#42 · S3 · unverified — Splitting an utterance splits the audio segment even if one part holds only metadata.**
- [ ] **#43 · S3 · unverified — Line breaks (Enter, Shift+Enter) can be inserted in the middle of a metadata tag.**
- [ ] **#44 · S3 · unverified — When `media-path` can't be found, the media refresh dialog doesn't update it.**
- [ ] **#45 · S3 · unverified — Importing a media by drag and drop should open the video widget.**
- [ ] **#46 · S3 · valid in code — Dropping text from an external application does nothing** (`TextEditWidget.dropEvent`: the `event.source() == None` branch is a `pass`, `src/ui/text_widget.py:~845`).
- [ ] **#47 · S3 · valid — `deleteSentence` doesn't delete the block's `userData`** (`src/ui/text_widget.py:~301`, `# TODO: fix this`). It sets `None` only when the new block is empty. Used by `DeleteUtterance`/`DeleteSegments` commands.
- [ ] **#48 · S4 · valid — Unintuitive behaviour when pressing Enter with a selection** (`src/ui/text_widget.py:~1111`): the selection is deleted without splitting.
- [ ] **#49 · S2 · valid in code — `TextAligner.autoAlign` leaks signal connections.** `self.recognizer.finished.connect(start_alignment)` (and the progress lambda) are never disconnected. After one auto-align that needed a hidden transcription, any later transcription that finishes re-runs the old `start_alignment` closure on stale blocks and pushes unexpected `AlignBlockWithSegment` commands. Use a one-shot connection (`Qt.SingleShotConnection`) or disconnect in `on_alignment_complete` / cancel. (`src/services/aligner.py`)
- [ ] **#50 · S2 · valid in code, needs repro — Auto-align can attach segments to the wrong blocks.** `TextAlignerWorker.run` only appends a segment for a `||` separator when `segment_tokens` is non-empty, so a sentence that normalizes to no words (only punctuation, `*`, metadata) yields no entry, `segments` becomes shorter than `blocks`, and `on_alignment_complete` indexes `blocks[i]` with a shifted `i`. Append `None` for empty groups.
- [ ] **#51 · S2 · valid — "Clear current file cache → Scenes" deletes the transcription instead of the scenes.** In `CachePanel.clearCurrentCache` the scenes branch computes `cache._get_transcription_path(...)` and unlinks it; it should use `_get_scenes_path`. (`src/ui/parameters_dialog.py:~1120`)
- [ ] **#52 · S2 · unverified (check intent) — Documents that were never saved as `.ali` are never autosaved.** `MainWindow.auto_save` returns when `file_path` is None or not `.ali`, and `openMediaFile` sets `file_path = media_path`. Work done after importing a media (transcription, manual alignment) is lost on a crash before the first save, and the new crash-recovery can't help. Decide whether to autosave next to the media (or in the user data dir) for unsaved documents.
- [ ] **#53 · S3 · valid — `WaveformWidget.zoomOut` raises `ZeroDivisionError` when no media is loaded** (`min_ppsec = self.width() / self.audio_len` with `audio_len == 0`; the toolbar zoom buttons are always enabled).
- [ ] **#54 · S3 · valid — `calculate_fingerprint` raises `ZeroDivisionError` for files smaller than 4096 bytes** (`n_blocks == 0`, then `file_size // n_blocks`). (`src/cache_system.py`)
- [ ] **#55 · S3 · valid — `FileManager.export_to_text_format`: if `format_eaf` raises, `data` is unbound** and the next line (`logger.debug(data)`) raises `UnboundLocalError`. Return after logging the error.
- [ ] **#56 · S3 · valid — Cache I/O is quadratic during transcription, and in-memory caches go stale.** `commit_transcription_to_cache` → `set_media_transcription` rewrites the whole `.tsv`, then `update_media_metadata` rewrites the whole media JSONL, for every recognized utterance (`append_media_transcription` exists but is unused). `get_doc_metadata` also saves on every read. Also `CachePanel` clearing deletes files but not `cache.transcriptions_cache`, so the old transcription stays in memory. Also called from the recognizer thread while the GUI thread reads it (no lock).
- [ ] **#57 · S3 · unverified — Inconsistent defaults in `getPrevSegmentId` / `getNextSegmentId`.** With `segment_id=None`, prev uses `self.active_segment_id` (can be `None`, so it never matches) while next uses `waveform.active_segment_id`; in playhead mode next returns `sorted_segments[i]` (the segment under the playhead) rather than `i + 1`. Check callers (`moveHead`/`moveTail`, snapping markers, play next/previous).
- [ ] **#58 · S3 · unverified — `MainWindow.getUtterancesForExport` includes `METADATA_ONLY` blocks with `segment = None`** (and duplicates `DocumentController.getUtterancesForExport`, which only exports `ALIGNED`). Check that `format_srt` / `format_eaf` / `format_txt` accept `None`, then keep a single implementation.

## 4. Code quality (from `TODO` / `XXX` comments)

- [ ] **#60 · S4 · valid — `AlignWithSelectionCommand` needs a rewrite** (`src/commands.py:~178`, `# TODO: Rewrite this`).
- [ ] **#61 · S4 · valid — Reverse the dependencies between `DocumentController` and the text/waveform widgets** (`src/main.py:~263`). The controller still gets widgets via `setTextWidget` / `setWaveformWidget` and pokes their state (`waveform.must_redraw`, `active_segment_id`, `resizing_state`...); widgets in turn use `self.main_window` (e.g. `TextEditWidget.contextMenuEvent` calls `main_window.waveform`). Protocols in `src/interfaces.py` are the intended seam.
- [ ] **#62 · S4 · valid — `DocumentController.loadData` seems slow** (`src/document_controller.py:~145`; also `getBlockById` is a linear scan of all blocks). Profile with `python main.py --profile` on a long `.ali` first.
- [ ] **#63 · S4 · valid — Move `TextEditWidget.setSentenceText` into `JoinUtterancesCommand`** (`src/ui/text_widget.py:~173`). Note it is also used by `src/commands.py:111` and `:162`, so check both uses before moving; the comment is partly outdated.
- [ ] **#64 · S4 · valid — Replace `showError` with a signal** (`src/file_io/dialogs.py:~288`). It is part of `FilePromptsInterface`.
- [ ] **#65 · S4 · unverified — Consider `QAudioDecoder` instead of the current waveform decoding** (`src/main.py:~1400`, `## XXX`). Only worth it if #35 turns out to come from the current approach.
- [ ] **#66 · S4 · unverified — Is the video layout refresh in `onPositionChanged` in the right place?** (`src/main.py:~1780`, `# XXX`). Candidate for a handler on the video widget itself.
- [ ] **#67 · S4 · valid — Dead / duplicated code.** `VoskFileTranscriptionWorker` is unused (only a commented-out block in `aligner.py`) and duplicates `RecognizerWorker.transcribe_file`, whose ffmpeg-to-Vosk streaming is itself copied three times in `transcriber.py`; `CacheSystem.append_media_transcription` is unused; `MainWindow.getSubtitleAtPosition` duplicates `DocumentController.getSubtitleAtPosition`. Pick one implementation of each.
- [ ] **#68 · S4 · valid — Replace debug `print()` calls with `logger.debug`** (`main.py`: `print(args)`, `print(media_metadata)`, `print(f"{doc_metadata=}")`...; `commands.py`; `text_widget.py` `changeTextFormat`/`insertFromMimeData`; `document_controller.py:_split_utterance`; `waveform_widget.py:updateThemeColors`).
- [ ] **#69 · S3 · valid — Opening the Render dialog freezes the UI on long documents** (`FUTURE` only): `CaptionRenderer.__init__` → `_set_document` runs `align_text_with_vosk_tokens` for every block on the GUI thread. That function is also O(words × tokens) `jiwer.cer` calls, which makes whole-file auto-align slow.

---

## Done / stale

- [x] **#90 · stale — Paste from an external text crashed with `'TextEditWidget' has no attribute 'cursor_pos'`.** `TextEditWidget.paste` now uses `self.textCursor()` (old path `src/text_widget.py` no longer exists). Reopen as a new task if pasting still fails.
- [x] **#91 · stale — Asynchronous loading of hunspell.** Done: `src/hunspell.py` loads spylls asynchronously.
- [x] **#92 · stale — Export of individual segments.** Done: `src/exports/` and `src/services/segment_exporter/`.
- [x] **#93 · done — Packaging fixes (spec, version via `tomllib`, `copy_metadata`, CI workflows).**
- [x] **#33 · done — "Adapt to subtitles" removed formatting (italics) from segments split by the subtitle rules.** `apply_subtitle_rules` used `block.text()`; it now slices the block's formatted fragments around the split and rebuilds HTML with `fragments_to_html`. Also fixed `fragments_to_html` crashing (`TextFormat` not orderable) on text that is both bold and italic. Test: `tests/test_document_controller.py::test_subtitle_rules_keep_formatting`.
