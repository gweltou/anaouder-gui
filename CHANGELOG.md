# CHANGELOG

## [Unreleased]

* Fixed sentence still highlighted as aligned after undoing an alignment
* Zooming the waveform is centered on the playhead when following it
* Trackpad drag and zoom on waveform
* Better waveform (looks and optimization)
* Progress bar in block number's column (left of text)
* Progress dialog with sequential tasks (as in transcribe -+> auto align)
* "Close file" command in file menu
* Fixed and optimized auto-segment algorithm
* Fixed auto-align command on Windows
* Set "preferences" shortcut to standard "ctrl+,"
* Sets 'media-path' metadata automatically
* Fixed shortcut hints in menus on macOS
* Length of longest line in segment displayed in status bar
* Fixed text formatting at wrong character offset
* File manager refactoring
* Global terminal logger
* Document auto-rescue after a crash
* Autosaves newer than the last manual save are removed when closing a document
* "Adapt to subtitles" keeps italics and bold when splitting a segment into two lines
* Fixed auto-align giving timings to the wrong sentences when a sentence has no words (only punctuation or metadata)
* Fixed auto-align running again by itself after a later transcription
* "Clear cache → Scenes" no longer deletes the transcription instead of the scenes
* Fixed a crash when zooming the waveform before a media file is loaded
* The waveform view no longer scrolls past the start or end of the media (wheel scrolling, following the playhead)
* Fixed an error when the EAF export fails

## [1.1] 2026-05-01

* Auto-align sentence function
* Asynchronous Hunspell dictionary loading
* "Hidden transcription" opereration in menu
* More flexible crop head and crop tail operations
* Better "Adapt to subtitles" dialog
* Line number area
* Timecode display with direct input
* Improved visibility of the splitters handles
* Media total duration in status bar
* "new line" and "em dashes" buttons
* Changed icon for del segment
* Fixed missing translations
* Better document state save & restore
* Better drag & drop support
* Better save error handling
* Support for embedded timecodes in video files
* Changed downloaded models checksum to SHA256

## [1.0] 2025-11-20
