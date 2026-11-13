# TODO

Single list of pending work for Anaouder: packaging chores, features, bugs and `TODO`/`XXX` comments found in the code.
It merges `docs/TODO.txt` (old, French, partly outdated) and the comments in `anaouder/`.
Last audit: 2026-11-13 (re-checked against a full read of the largest source files; see #49-#58, #67-#69; #71-#80 come from the old `PLAN.md` review).

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

- [x] **#1 · S2 · done — Rename the `src` package to `anaouder`.**
  Done: steps 1–6, `.gitignore` (`*.egg-info/`, `.coverage`), `CLAUDE.md`, `.ts` source locations, local `docs/internationalization.txt`; tests, app launch and a Linux PyInstaller build (bundles `anaouder.lang.*`, binary starts) OK.
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
- [ ] **#3 · S4 · valid — Declare missing dependencies in `pyproject.toml`.** `jiwer` (used by `services/aligner.py`) and `numpy` are imported but not declared. Also add a `test` optional-dependency group (`pytest`, plus `pytest-qt` if adopted, see #78). Verify with a clean venv.
- [ ] **#4 · S4 · valid — Spec small cleanups** (`anaouder.spec`): `argv_emulation=True` on all platforms, `COLLECT upx=True` vs `EXE upx=USE_UPX`, stale module docstring, manual `hiddenimports`.
- [ ] **#5 · S3 · valid — `test_remove_fillers` fails.** `tests/test_adapt_subtitles.py::test_remove_fillers` gets `\xa0` before `?` instead of a plain space. Decide whether the code or the test is wrong.
- [ ] **#6 · S4 · valid — `building/Windows/anaouder_installer.iss` hardcodes `MyAppVersion "1.1.1"`** (CI overrides it, local builds don't). Keep in sync or drop the default.
- [ ] **#70 · S4 · valid — Create a CI workflow for macOS with Apple Silicon.**
- [ ] **#71 · S4 · valid — Remove the duplicate segment exporter.** `anaouder/exports/segment_exporter.py` (417 lines, dialog + exporter in one file) is an older copy of `anaouder/services/segment_exporter/` (`dialog.py` + `segment_exporter.py`). Only the `services` version is imported (`anaouder/main.py:~110`). `git rm -r anaouder/exports/` after checking nothing in `tests/` relies on it, and update the "Segment export" line in `CLAUDE.md`.
- [ ] **#72 · S4 · valid — Tidy untracked root files.** `header.txt`, `header2.txt`, `list_files.sh`, `README_old.md`, `tutorial.ali`, `res/mod_implij.{rtf,txt}` are untracked at the root. Commit what is useful (e.g. `tutorial.ali` as an example document, `build_macos-x86.sh` into `building/macOS/`), delete the rest.
- [ ] **#73 · S4 · valid — Keep release binaries out of the tree.** `building/Linux/Anaouder-1.1_linux_x86_64.AppImage` and `building/Linux/appimagetool-x86_64.AppImage` are untracked but not ignored (`building/` is 182 MB, `dist/` 111 MB). Ignore `*.AppImage`, publish releases on GitHub Releases, and have `build_linux_appimage.sh` download `appimagetool` instead of expecting it in the tree.
- [ ] **#74 · S4 · valid — `.gitignore` ignores all of `docs/` and `examples/`.** `docs/internationalization.txt` is referenced by `CLAUDE.md` but can't be committed. Un-ignore `docs/` (or at least that file) and `examples/` if they hold anything worth sharing. (`docs/model_list.json` is no longer read at runtime: the Breton model list comes from `ostilhou`.)
- [ ] **#75 · S4 · valid — Consolidate packaging scripts.** `install_{linux.sh,macOS.command,win.bat}` and `start_{linux.sh,macOS.command,win.bat}` sit at the root, `build_macos-x86.sh` (untracked) at the root, the rest in `building/{Linux,macOS,Windows}`. Move everything into `building/<platform>/` (or `packaging/`), keeping at the root only the entry points users really run, and update `README*`/CI. There is also no Linux CI workflow (only `package_macos_intel.yml` and `package_win64.yml`; see #70).

## 2. Features

- [ ] **#10 · S3 · valid — Search and replace (Ctrl+F).** `MainWindow.search()` is a stub that prints "search tool" (`anaouder/main.py` ~2399, comment `## Search TODO` ~170). Use a modeless `QDialog`.
- [ ] **#11 · S3 · unverified — Add the `media-source` metadata automatically when saving `.ali`** if not already present. No code references `media-source`; `media-path` is written in `anaouder/file_io/file_manager.py`. Clarify the intended difference between the two before implementing.
- [ ] **#12 · S4 · unverified — Hide the `audio-path` metadata / insert it automatically when opening a media.** `audio-path` is read as a legacy alias and stripped on save (`file_manager.py` ~203-410); the note probably predates `media-path`. Confirm whether `audio-path` is still wanted.
- [~] **#13 · S3 · partly done — Delete a segment only, keeping the text.** Already implemented: `DeleteSegmentsCommand` / `DocumentController.deleteSegments` and the "Delete audio segment" action in the waveform and text context menus. Left: a shortcut (Shift+Del) and a toolbar button (`QAction` `delete_segment` has no shortcut in `anaouder/actions.py`).
- [ ] **#14 · S3 · valid — Add a word to the autocorrect dictionary** (from the spellcheck context menu).
- [ ] **#15 · S3 · valid — Substitution dictionary** (user-defined replacements).
- [ ] **#16 · S4 · unverified — Enable the subtitles margin automatically when a `subtitles` tag is found in the document.** The tag is filtered in `video_widget.py:132` and `file_io/srt.py:45`, nothing enables a margin from it.
- [ ] **#17 · S3 · valid — Enforce the media cache size limit.** The spinbox in `anaouder/ui/parameters_dialog.py:~961` is disabled (`# TODO`), the value is saved under `cache/media_cache_size`, and `cache_system.py` has no eviction. Implement eviction (oldest first), then enable the spinbox.
- [ ] **#18 · S3 · valid — Full-screen mode for the video widget.** No `showFullScreen` anywhere.
- [ ] **#19 · S3 · unverified — CSV export.** Check `anaouder/exports/` first; not listed in CLAUDE.md formats.
- [ ] **#20 · S3 · valid — Whisper support as an alternative ASR backend** (and multilingual Fr/En/Cy models). No reference in code; needs a model-type abstraction (see #21).
- [ ] **#21 · S3 · valid — Model library file with several sources** (URL and local paths). Proposed format (YAML or JSON): `file_version`, and per model `name`, `lang` (comma list or `*`), `type` (`kaldi-vosk`, `whisper-onnx`, `pyannote`), `footprint` (MB RAM), `download_url`, `modelcard`, `desc_<lang>`, `sha256`. Related: `anaouder/services/model_manager.py`, `docs/model_list.json`.
- [ ] **#22 · S4 · valid — Localize `convert_quotation_marks`** to the document language's quotation marks (`anaouder/services/adapt_subtitles.py:~343`).

## 3. Bugs

Bugs from `docs/TODO.txt` have not been re-reproduced unless stated; `unverified` means "check before fixing".

- [ ] **#30 · S2 · unverified — Joining two segments sometimes fails** (`anaouder/commands.py:~135`, `# TODO: fix bug when joining (sometimes)` in `JoinUtterancesCommand.redo`). Needs a repro.
- [ ] **#31 · S2 · unverified — Density colour not refreshed after joining two segments** (probably the commented-out `waveform.refreshSegmentInfo()` in `JoinUtterancesCommand.undo`, `anaouder/commands.py:~137`).
- [ ] **#32 · S2 · valid — Special tokens disappear when a word is replaced in the same block** (`ReplaceTextCommand`, `anaouder/commands.py:~576`). `new_text` should be HTML including formatting and metadata.
- [ ] **#34 · S1 · unverified — Crash on first start on Windows when offline.** Look at model list fetching / `ostilhou` data download at startup.
- [ ] **#35 · S1 · unverified — Segfault in `libswresample` (`QFFmpeg::AudioR…`) when playing 24-bit PCM stereo 48 kHz files** (`pcm_s24le`). Qt Multimedia/FFmpeg issue; consider converting such media on import, or a warning. Also: no transcription with these formats.
- [ ] **#38 · S3 · unverified — Multi-selection on the waveform** needs fixing (description is vague; reproduce and rewrite this entry).
- [ ] **#39 · S3 · unverified — Warn when the file given by `audio-path`/`media-path` doesn't exist.** `file_manager.py:~135` already calls `showError` in one path; check the others.
- [ ] **#40 · S3 · unverified — "Recognize" on several selected segments transcribes in reverse order.** Suspect: `MainWindow.transcribeAction` iterates `waveform.active_segments` in selection order; sort by start time.
- [ ] **#41 · S3 · unverified — First save: the system dialog's file name is empty** (`anaouder/main.py:~1569`, `# TODO: When saving, the folder and basename are not set`).
- [ ] **#42 · S3 · unverified — Splitting an utterance splits the audio segment even if one part holds only metadata.**
- [ ] **#43 · S3 · unverified — Line breaks (Enter, Shift+Enter) can be inserted in the middle of a metadata tag.**
- [ ] **#44 · S3 · unverified — When `media-path` can't be found, the media refresh dialog doesn't update it.**
- [ ] **#45 · S3 · unverified — Importing a media by drag and drop should open the video widget.**
- [ ] **#46 · S3 · valid in code — Dropping text from an external application does nothing** (`TextEditWidget.dropEvent`: the `event.source() == None` branch is a `pass`, `anaouder/ui/text_widget.py:~845`).
- [ ] **#47 · S3 · valid — `deleteSentence` doesn't delete the block's `userData`** (`anaouder/ui/text_widget.py:~301`, `# TODO: fix this`). It sets `None` only when the new block is empty. Used by `DeleteUtterance`/`DeleteSegments` commands.
- [ ] **#48 · S4 · valid — Unintuitive behaviour when pressing Enter with a selection** (`anaouder/ui/text_widget.py:~1111`): the selection is deleted without splitting.
- [ ] **#52 · S2 · unverified (check intent) — Documents that were never saved as `.ali` are never autosaved.** `MainWindow.auto_save` returns when `file_path` is None or not `.ali`, and `openMediaFile` sets `file_path = media_path`. Work done after importing a media (transcription, manual alignment) is lost on a crash before the first save, and the new crash-recovery can't help. Decide whether to autosave next to the media (or in the user data dir) for unsaved documents.
- [ ] **#54 · S3 · valid — `calculate_fingerprint` raises `ZeroDivisionError` for files smaller than 4096 bytes** (`n_blocks == 0`, then `file_size // n_blocks`). (`anaouder/cache_system.py`)
- [ ] **#56 · S3 · valid — Cache I/O is quadratic during transcription, and in-memory caches go stale.** `commit_transcription_to_cache` → `set_media_transcription` rewrites the whole `.tsv`, then `update_media_metadata` rewrites the whole media JSONL, for every recognized utterance (`append_media_transcription` exists but is unused). `get_doc_metadata` also saves on every read. Also `CachePanel` clearing deletes files but not `cache.transcriptions_cache`, so the old transcription stays in memory. Also called from the recognizer thread while the GUI thread reads it (no lock).
- [ ] **#57 · S3 · unverified — Inconsistent defaults in `getPrevSegmentId` / `getNextSegmentId`.** With `segment_id=None`, prev uses `self.active_segment_id` (can be `None`, so it never matches) while next uses `waveform.active_segment_id`; in playhead mode next returns `sorted_segments[i]` (the segment under the playhead) rather than `i + 1`. Check callers (`moveHead`/`moveTail`, snapping markers, play next/previous).
- [ ] **#58 · S3 · unverified — `MainWindow.getUtterancesForExport` includes `METADATA_ONLY` blocks with `segment = None`** (and duplicates `DocumentController.getUtterancesForExport`, which only exports `ALIGNED`). Check that `format_srt` / `format_eaf` / `format_txt` accept `None`, then keep a single implementation.

## 4. Code quality (from `TODO` / `XXX` comments)

- [ ] **#60 · S4 · valid — `AlignWithSelectionCommand` needs a rewrite** (`anaouder/commands.py:~178`, `# TODO: Rewrite this`).
- [ ] **#61 · S4 · valid — Reverse the dependencies between `DocumentController` and the text/waveform widgets** (`anaouder/main.py:~263`). The controller still gets widgets via `setTextWidget` / `setWaveformWidget` and pokes their state (`waveform.must_redraw`, `active_segment_id`, `resizing_state`...); widgets in turn use `self.main_window` (e.g. `TextEditWidget.contextMenuEvent` calls `main_window.waveform`). Protocols in `anaouder/interfaces.py` are the intended seam.
- [ ] **#62 · S4 · valid — `DocumentController.loadData` seems slow** (`anaouder/document_controller.py:~145`; also `getBlockById` is a linear scan of all blocks). Profile with `python main.py --profile` on a long `.ali` first.
- [ ] **#63 · S4 · valid — Move `TextEditWidget.setSentenceText` into `JoinUtterancesCommand`** (`anaouder/ui/text_widget.py:~173`). Note it is also used by `anaouder/commands.py:111` and `:162`, so check both uses before moving; the comment is partly outdated.
- [ ] **#64 · S4 · valid — Replace `showError` with a signal** (`anaouder/file_io/dialogs.py:~288`). It is part of `FilePromptsInterface`.
- [ ] **#65 · S4 · unverified — Consider `QAudioDecoder` instead of the current waveform decoding** (`anaouder/main.py:~1400`, `## XXX`). Only worth it if #35 turns out to come from the current approach.
- [ ] **#66 · S4 · unverified — Is the video layout refresh in `onPositionChanged` in the right place?** (`anaouder/main.py:~1780`, `# XXX`). Candidate for a handler on the video widget itself.
- [ ] **#67 · S4 · valid — Dead / duplicated code.** `VoskFileTranscriptionWorker` is unused (only a commented-out block in `aligner.py`) and duplicates `RecognizerWorker.transcribe_file`, whose ffmpeg-to-Vosk streaming is itself copied three times in `transcriber.py`; `CacheSystem.append_media_transcription` is unused; `MainWindow.getSubtitleAtPosition` duplicates `DocumentController.getSubtitleAtPosition`. Pick one implementation of each.
- [ ] **#68 · S4 · valid — Replace debug `print()` calls with `logger.debug`** (`main.py`: `print(args)`, `print(media_metadata)`, `print(f"{doc_metadata=}")`...; `commands.py`; `text_widget.py` `changeTextFormat`/`insertFromMimeData`; `document_controller.py:_split_utterance`; `waveform_widget.py:updateThemeColors`).
- [ ] **#69 · S3 · valid — Opening the Render dialog freezes the UI on long documents** (`FUTURE` only): `CaptionRenderer.__init__` → `_set_document` runs `align_text_with_vosk_tokens` for every block on the GUI thread. That function is also O(words × tokens) `jiwer.cer` calls, which makes whole-file auto-align slow.
- [ ] **#76 · S4 · valid — Break up `MainWindow`** (`anaouder/main.py`, ~2770 lines). In order: move menu/toolbar construction (the `_create_*` methods, ~600 lines) into `ui/menus.py`; move the transcribe → align orchestration (`transcribeAction`, `toggleHiddenTranscription`, `updateUtteranceTranscription`, `newSegmentTranscribed`) into a controller in `services/`; move the file open/save glue (`onOpenFile`, `askCloseFile`, `_save/_load_document_state`) next to `file_io/file_manager.py`; then move `MainWindow` itself to `ui/main_window.py`, leaving `main()` and `TranslatedApp` in `anaouder/main.py`. Do it one step per commit. Related: #61, #67. Next candidates: `ui/text_widget.py` (~1550 lines) and `ui/parameters_dialog.py` (~1180 lines, one module per tab).
- [ ] **#77 · S4 · valid — Sort the top-level modules of `anaouder/`.** `transcriber.py` → `services/`; `auto_segment.py` → `audio/` (it only wraps `audio/audio_splitter.py`); `splitter.py` is a `QSplitter` widget (not audio) → `ui/`. Optionally group `settings.py`, `strings.py`, `utils.py`, `version.py`, `cache_system.py` in a `core/` package. Do it after #76, which touches the same imports, and update `CLAUDE.md`.
- [ ] **#78 · S4 · valid — Test setup.** Add `tests/conftest.py` with a session-wide `QApplication` fixture (or adopt `pytest-qt`) and set `QT_QPA_PLATFORM=offscreen` by default (`os.environ.setdefault` in `conftest.py`); several test modules build their own app, and `test_adapt_subtitles.py` builds a whole `MainWindow`. Move the `test_file.*` fixtures into `tests/data/`.
- [ ] **#79 · S4 · valid — Test coverage gaps.** No tests for `services/caption_renderer.py`, `services/task.py` (`TaskQueue` chaining/cancel), `services/model_manager.py`, `services/segment_exporter/`, or the `txt` / `rtf` formats in `file_io/`.
- [ ] **#80 · S4 · valid — One convention for UI strings.** Translatable strings are spread across `strings.py`, `lang/` and `self.tr()` / `QCoreApplication.translate` calls in ~18 modules, with `.ts` files in `translations/`. Pick one (probably `tr()` + `strings.py` for shared strings) and document it in `docs/internationalization.txt`.

---

## Done / stale

- [x] **#81 · S2 · done — Undoing an alignment left the sentence highlighted as aligned.** Undo of `AlignWithSelectionCommand` / `AlignBlockWithSegmentCommand` restored the block metadata with `setBlockMetadata`, which didn't rehighlight, and before the segment was removed. `setBlockMetadata` now rehighlights the block and both undos remove the segment first. Tests in `tests/test_commands.py`.
- [x] **#82 · S3 · done — Zoom ignored "follow playhead".** `WaveformWidget.zoomIn` / `zoomOut` pivoted on the mouse position even when following the playhead; they now center the view on the playhead in that mode (`_set_zoom`). Tests in `tests/test_waveform_widget.py`.
