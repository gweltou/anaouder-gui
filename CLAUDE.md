# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Anaouder is a PySide6 (Qt) desktop app for transcribing and subtitling audio/video, primarily in Breton (other languages support is planned). Offline speech recognition uses Vosk. Python >= 3.12, GPLv3. UI strings and docs are in Breton/French/English.

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .            # runtime deps (see pyproject.toml); `.[build]` adds pyinstaller
python main.py              # run the app; --debug/-d for DEBUG logging, --profile for cProfile
pytest                      # all tests (pytest.ini only configures log format)
pytest tests/test_commands.py::test_name   # single test
```

- Tests import `anaouder.*` and instantiate Qt objects (e.g. `MainWindow`, `QApplication`), so they need a Qt platform (use `QT_QPA_PLATFORM=offscreen` headless). `test_*.wav/.m4a/.srt/.eaf/.ali` in `tests/` are fixtures.
- Translations: edit `translations/anaouder_{br,fr}.ts`, then compile to `.qm` (see `docs/internationalization.txt` for the `pyside6-lupdate` / `pyside6-lrelease` commands).
- Packaging: PyInstaller spec (`anaouder.spec`), `build_macos-x86.sh`, `building/`. `main.py` handles the `sys._MEIPASS` case to locate bundled static ffmpeg. User-facing release notes go in `CHANGELOG.md` under `[Unreleased]`.

## Architecture

Entry: `main.py` (ffmpeg setup, logging) → `anaouder/main.py` (`main()`, `TranslatedApp`, and the very large `MainWindow` that wires everything together).

**Document model.** The transcript lives in a `QTextDocument` inside the text editor widget (`anaouder/ui/text_widget.py`); each text block is an "utterance". Timing data is kept separately: `DocumentController` (`anaouder/document_controller.py`) owns `segments: dict[SegmentId, [start, end]]` and links blocks ↔ segments via `MyTextBlockUserData` (a `seg_id` plus metadata). A block's `BlockType` (`EMPTY_OR_COMMENT`, `METADATA_ONLY`, `ALIGNED`, `NOT_ALIGNED`) says whether it has a segment. The controller also owns the `QUndoStack`.

**Undo/redo via commands.** Edits that change both text and segments must go through `QUndoCommand` subclasses in `anaouder/commands.py` (add/delete/resize/join segments, align block, etc.), pushed on `document_controller.undo_stack`, so text and segment state stay consistent.

**Protocols in `anaouder/interfaces.py`.** `DocumentInterface`, `TextEditorInterface`, `WaveformInterface`, `MainWindowInterface`, `FilePromptsInterface` are `typing.Protocol`s used to decouple modules (commands, aligner, file manager) from concrete widgets and to make them testable. When adding a method that other modules call on these objects, update the Protocol too.

**Background work.** Long tasks are `QThread`-based workers (`TaskWorker` / `TaskQueue` in `anaouder/services/task.py`) allowing sequential chains (e.g. transcribe → auto-align) with a progress dialog. Workers: `transcriber.py` (Vosk transcription + live recognizer), `services/aligner.py` (aligns text to Vosk tokens, uses `jiwer`), `services/caption_renderer.py` (render/burn subtitles into video via ffmpeg), `services/scene_detector.py`. `services/media_player_controller.py` wraps Qt multimedia playback.

**File I/O.** `anaouder/file_io/` has format modules (`srt`, `eaf`, `txt`, `rtf`) plus `file_manager.py` (open/save/autosave "document auto-rescue"/backups) and `dialogs.py` (implements `FilePromptsInterface`). Native format is `.ali` (text with embedded timing metadata). Segment export lives in `anaouder/exports/` and `anaouder/services/segment_exporter/`.

**Languages.** `anaouder/lang/` (`br`, `fr`, `cy`) define per-language `Language` objects (text post-processing, alignment normalization, filler removal, model lists). Switched with `lang.loadLanguage()`. Vosk model management (lists, cache paths, download URLs, deletion) is in `anaouder/lang/__init__.py`, with the download/delete UI in `ui/parameters_dialog.py` (`ModelsPanel`, `DownloadProgressDialog`); `services/model_manager.py` is an untracked, unused draft (see TODO #21, #72). The Breton model list comes from the `ostilhou` package (`anaouder/lang/br.py`), not from `docs/model_list.json`. Spellcheck: `anaouder/hunspell.py` (spylls, loaded asynchronously).

**Other.** `cache_system.py` stores per-media-file (fingerprint-based) transcription/waveform data in the user cache dir; `settings.py` persists preferences; `strings.py` holds shared UI strings; `ui/` contains widgets (waveform, text highlighter, timecode display, theme, dialogs).

## Task tracking

`TODO.md` (repo root) is the single list of pending tasks, bugs and code `TODO`s, each with a number, a status marker (`[ ]` / `[~]`), a severity (S1–S4) and a validity check. Read it before non-trivial work, reference tasks by number (e.g. "fix #30"), mark it `[~]` when you start, and when it is finished delete its entry (reference the number in the commit message) and remove the matching `TODO` comment in the code. Never reuse a task number: new tasks take the next number after the "highest number used" noted in the file, which you then bump. The application package is `anaouder` (renamed from `src` in task #1); import as `anaouder.<module>`.

## Gotchas

- `tests/test_adapt_subtitles.py::test_remove_fillers` currently fails (a non-breaking space before `?` in the output, TODO #5); other tests pass.

## Application structure

Largest files in `anaouder/` (~19k lines of Python total), each read in full. Line counts are approximate.

### `anaouder/main.py` (~2770 lines)
- **`MainWindow(QMainWindow)`** is the composition root and a large god-object. `__init__` runs `_initialize_state` → `_initialize_components` → `_configure_window` → `_init_ui` → `_connect_signals` → `_restore_settings`.
  - Components it creates and owns: `Prompts`, `FilePrompts`, `FileManager`, `ActionManager`, `DocumentController`, `TextEditWidget`, `WaveformWidget`, `VideoWidget`, `MediaPlayerController`, `TranscriptionService`, `TextAligner`, the autosave `QTimer` (6 s tick; the real interval is enforced in `FileManager.auto_save`).
  - Menus and toolbars are built by hand in `_create_*` methods (about 600 lines of layout code). Most `action.*_requested` signals from `ActionManager` are wired to `MainWindow` slots in `_connect_signals`.
  - File lifecycle: `onOpenFile` is the hub for media, `.ali`, `.srt` and `.eaf`. `askCloseFile` handles the save prompt, clears newer autosaves and writes the document state to the cache. `_save_document_state` / `_load_document_state` persist cursor, playhead, waveform zoom and display toggles through `cache.*_doc_metadata`. `openMediaFile` loads the waveform (cached or via `get_samples`), reads fps/duration/timecode offset via `get_audiofile_info`, and sets the status-bar transcription LED.
  - Crash recovery: the `safely_closed` setting is reset at startup and set again in `closeEvent`. If it was left false, `_recover_after_crash` offers to reopen the last autosave.
  - Playback logic lives here, not in `MediaPlayerController`: `onPlayerPositionChanged` (looping and selection end), `onPlaySegmentAction` (double-press detection), `playNext/PreviousSegment`.
  - Transcription glue: `transcribeAction`, `toggleHiddenTranscription`, `updateUtteranceTranscription` (pushes `CreateNewEmptyUtteranceCommand` + `ReplaceTextCommand`), `newSegmentTranscribed` (bypasses the undo stack, snaps to fps).
  - Status bar: `updateSegmentInfoResizing` builds the start/end/duration/length/density line and highlights values that break the subtitle rules.
  - Dead or stub code: `search()` is a stub, `getUtterancesForExport` duplicates `DocumentController.getUtterancesForExport` (with a different block-type filter), and some features are gated behind `settings.FUTURE`.
- **`TranslatedApp(QApplication)`** has `switch_language`, which installs the `.qm` translator and re-initialises `app_strings`. `main()` parses `filename`, `--debug` and `--last`, then creates the app and the window.

### `anaouder/document_controller.py` (~1050 lines): `DocumentController(QObject)`
- State: `segments: dict[SegmentId, Segment]`, a lazily sorted list (`must_sort` flag, `getSortedSegments`), `id_counter`, `selected_segments`, `active_segment_id`, `undo_stack`, plus references to the text and waveform widgets (set via `setTextWidget` / `setWaveformWidget`, which also connect their signals).
- Block ↔ segment link: `getBlockId`, `setBlockId`, `getBlockById` (linear scan of the document), `getBlockType` (strips `#` comments and `{metadata}`), `get/set/updateBlockMetadata`.
- Segment CRUD (`addSegment`, `updateSegment`, `removeSegment`) always set `must_sort` and `waveform.must_redraw`. These are the low-level mutators that commands call. UI code should go through commands instead.
- Queries: previous/next segment (relative to the active one or the playhead), `getSegmentsAtTime`, `getSegmentsAtTimeOffsets` (fade offsets for the renderer), utterance density (chars/s, cached in block metadata), and cached-transcription tokens for a segment (`getTranscriptionForSegment`, with one-entry memoization).
- Edits that push commands: `splitUtteranceAtCharPos` / `AtTimePos` / `AtPlayhead` (try "smart split" from cached Vosk tokens, then fall back to ratio or empty-right-half) → `_split_utterance`, which is a macro of Delete + Add + Insert commands. Also `joinUtterances`, `deleteUtterances`, `deleteSegments`, `moveHead`, `moveTail`.
- Selection sync between text and waveform: `select_utterances` (single entry point), `on_text_cursor_changed`, `select_from_waveform`. Also `loadData` / `getData` / `getDocumentState` for (de)serialising the document.

### `anaouder/commands.py` (~760 lines): `QUndoCommand`s
- Utterance-level (text + segment): `CreateNewEmptyUtteranceCommand`, `JoinUtterancesCommand`, `DeleteUtterancesCommand`, `AlignWithSelectionCommand` (marked "TODO: Rewrite this"), `AlignBlockWithSegment` (used by auto-align).
- Text-level: `InsertTextCommand` (id 0), `DeleteTextCommand` (id 1) and `InsertBlockCommand` (id 2) use `id()` + `mergeWith` for typing coalescing. `InsertBlockCommand.mergeWith` always returns False. `ReplaceTextCommand` (id 3) swaps a block's HTML. `MoveTextCursor` only moves the cursor.
- Segment-level: `AddSegmentCommand`, `ResizeSegmentCommand`, `DeleteSegmentsCommand`.
- Commands depend on the Protocols in `interfaces.py` rather than on concrete widgets. Several of them (`AlignWithSelectionCommand`, `ReplaceTextCommand`) still reach into widget internals or `print` debug output.

### `anaouder/ui/text_widget.py` (~1550 lines): `TextEditWidget(QTextEdit)`
- Built-in undo is disabled. Every edit goes through `document_controller.undo_stack`.
- `keyPressEvent` intercepts typing, Tab, undo/redo, cut/paste and zoom, then delegates to `_handle_return_key` / `_handle_delete_key` / `_handle_backspace_key`. These implement split/join semantics: Enter in the middle of an aligned block emits `split_utterance`, and Backspace/Delete at block edges emit `join_utterances` / `delete_utterances` or fall back to text commands.
- Rich text: `getBlockFragments` / `fragments_to_html` / `get_position_in_html` map between the QTextDocument (bold/italic char formats, `\u2028` line breaks) and the `<B>/<I>/<BR>` HTML-like markup used for storage, with a mask used for cursor mapping. `changeTextFormat`, `insertNewline`, `insertEmDash` and `replaceWord` build on them.
- Other: `insertBlock` (escapes `<TOKEN>` tags), `insertSentenceWithId` (inserts at the time-ordered position, outside the undo stack), `highlightUtterances`, `onCursorChanged` → `cursor_changed_signal(ids, active_id)`, the spell-check context menu, triple-click selection, the subtitle-margin overlay and the line-number bar (`LineNumberBar`). `Highlighter` is attached for alignment/density colouring and spell-check.

### `anaouder/ui/waveform/`
- `waveform_widget.py` (~1150 lines): `WaveformWidget(QWidget)` renders into a `QPixmap` on a 30 fps timer, only when `must_redraw` is set. It owns the view state (`ViewState`: `t_left`, `ppsec`, scroll velocity and goal), `active_segments` / `active_segment_id`, the free `_selection`, the `ResizeState`, and playhead/follow mode.
  - Smooth scrolling and zoom are animated in `_update`.
  - Mouse handling covers handle hit-testing (left/middle/right), drag-to-resize with neighbour bounds and frame snapping, selection creation, right-click playhead scrubbing, and wheel/pinch zoom. A resize is committed through `ResizeSegmentCommand` on release.
  - Emits signals (`select_segments`, `join_utterances`, `delete_utterances`, `playhead_moved`, `refresh_segment_info*`, ...) and has no direct dependency on `MainWindow` logic beyond `main_window` for a few lookups.
- `rendering.py` (~665 lines): a layered painter. `RenderContext` (immutable, rebuilt each frame; has `t_to_x` / `x_to_t`), `PenSet` (theme pens), `LayoutMetrics` (recomputed on resize), and `RenderLayer` subclasses drawn in order: `ProgressLayer`, `WaveformLayer` (caches a pixmap 3× viewport wide, rebuilt on zoom or when scrolling nears the edge), `TimelineLayer`, `SegmentsLayer` (inactive/active/selection rectangles, handles, snapping markers for min/max duration and target density), `SceneChangeLayer`, `PlayheadLayer`.
- Related modules in the same package: `data.py` (`WaveformData`, `ViewState`, `ResizeState`, `Handle`, `SegmentSide`, `SubtitleRules`).

### `anaouder/transcriber.py` (~620 lines)
- `RecognizerWorker(QObject)` lives on its own `QThread` (owned by `TranscriptionService`). It loads a Vosk model, streams ffmpeg PCM (16 kHz mono) into `KaldiRecognizer`, and emits `new_segment_transcribed` (whole file) or `segment_transcribed` (pre-existing segments). Both paths call `commit_transcription_to_cache`, which merges tokens into the cached transcription and updates `transcription_progress`.
- `TranscriptionService(QObject)` is the façade used by `MainWindow` and `TextAligner`: `loadModel`, `transcribeFile`, `transcribeSegments`, `stop`, `cleanup`. It re-exposes the worker's signals.
- `VoskFileTranscriptionWorker(TaskWorker)` is a near-duplicate of `transcribe_file` meant for `TaskQueue` chains. It is currently only referenced in a commented-out block of `aligner.py`.

### `anaouder/services/aligner.py` (~490 lines)
- Pure functions: `prep_sentence` (normalise text for comparison), `align_text_with_vosk_tokens` (Levenshtein-style DP over words with `jiwer.cer` substitution cost, cancellable), `can_smart_split` (CER < 0.5 gate), `smart_split_text` / `smart_split_time`.
- `TextAlignerWorker(TaskWorker)` aligns the concatenated unaligned sentences (separated by `||`) to tokens and emits one `[start, end]` per sentence.
- `TextAligner(QObject).autoAlign` is the orchestrator. It gets the unaligned blocks and time range from `DocumentController.getSelectedBlocksAndTimeRange`, runs a hidden transcription first if the cache is incomplete, then aligns, then pushes `AlignBlockWithSegment` commands in one macro, all behind a modal `ProgressDialog`.

### `anaouder/services/caption_renderer.py` (~885 lines)
- `CaptionRenderer` (Pillow-based, no Qt painting) reads per-block metadata (`{font: ...; fg-color: ...}`, parsed with ostilhou's `MetadataParser`) and renders PNG frames with open captions: word-level colour progress (`bg` / `fg` / `interpolation` / `word` via alignment), fade-in/out, positions, background colour or image sequences, and a per-word bitmap cache.
- `RendererWorker` renders a frame range. `VideoBurnerWorker` runs ffmpeg to overlay the PNG sequence on the source video and parses `-progress` output. Both are `TaskWorker`s chained by `TaskQueue` in `ui/render_dialog.py`, which is reachable from the "Render frames" menu entry only when `FUTURE` is set.

### `anaouder/file_io/file_manager.py` (~645 lines): `FileManager(QObject)`
- Reading: `read_file` dispatches by extension (`.ali`, `.srt`, `.eaf`, `.seg`/`.split`) and returns `{"document": [(text, segment|None)], "media-path": Path|None, ...}`. It finds or asks for the media file via `FilePromptsInterface`. `.ali` files embed timing as a trailing `{start: ...; end: ...}` and the media link as `{media-path: ...}`.
- Writing: `save_ali_file`, `export_to_text_format` (SRT/TXT/EAF via the sibling format modules).
- Autosave ("document auto-rescue"): `auto_save` writes `<dir>/<AUTOSAVE_FOLDER_NAME>/<stem>@YYYYmmdd_HHMMSS.ali`, skipping when the undo-stack index is unchanged or the interval hasn't elapsed, and prunes old backups. `get_unsaved_backups` returns the backups newer than the saved file; `_select_file_to_load` picks one (or asks the user); `clear_unsaved_backups` is called on close.
- Recent files are stored in `app_settings` and announced via `recent_files_updated`.

### `anaouder/cache_system.py` (~460 lines): `CacheSystem` (module-level singleton `cache`)
- Everything is keyed by `calculate_fingerprint` (SHA-256 over up to 8 × 4 KiB samples of the file, memoized).
- Two JSONL databases rewritten wholesale on change: media metadata (by fingerprint: duration, fps, transcription progress/completed, waveform size...) and document metadata (by absolute path: cursor, zoom, toggles). Separate folders hold transcriptions (`.tsv`), scenes (`.tsv`) and waveforms (`.npy`). Transcriptions also have an in-memory cache.
- Note that `get_doc_metadata` and `update_media_metadata` write to disk on every call.

### `anaouder/ui/parameters_dialog.py` (~1180 lines)
- `ParametersDialog` is a tab container exposing a `Signals` object (`update_ui_language`, `toggle_autosave`, `subtitles_*_changed`, `cache_*_cleared`) that `MainWindow.showParametersDialog` connects.
- Tabs: `GeneralPanel` (UI language, subtitle font/rect colours, autosave interval and count), `ModelsPanel` (list / download / delete Vosk models via `anaouder.lang`), `SubtitlesPanel` (min/max frames, min interval, auto-extend, margin, CPS; "Netflix default" vs custom), `CachePanel` (sizes on disk, clear per-file or global cache). `DownloadProgressDialog` downloads in a plain `threading.Thread`, checks SHA-256 and extracts zip/tar archives.
- Settings are written straight to `app_settings` (QSettings) as widgets change.

### Smaller modules worth knowing
`anaouder/services/task.py` (`TaskWorker`, `TaskQueue`), `services/media_player_controller.py`, `services/scene_detector.py` (`SceneDetectWorker`), `services/adapt_subtitles.py` (`AdaptUtterancesDialog`), `actions.py` (`ActionManager`: all `QAction`s and `*_requested` signals), `ui/theme.py`, `ui/text_highlighter.py`, `ui/video_widget.py`, `ui/dialogs.py`.

### Data flow in short
User edits in `TextEditWidget` or `WaveformWidget` → `DocumentController` methods or direct `undo_stack.push(...)` → `QUndoCommand`s mutate the `QTextDocument` and `DocumentController.segments` together (and set `must_redraw`) → the waveform repaints from `segments`, and `MainWindow` slots refresh the status bar and subtitle overlay. Long-running work (transcription, alignment, rendering, scene detection) runs on worker threads and reports back through signals that `MainWindow` connects.
