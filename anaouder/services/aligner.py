"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025-2026 Gweltaz Duval-Guennoc (gwel@ik.me)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import re
from math import inf

import jiwer
from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtGui import QTextBlock

from anaouder.cache_system import cache
from anaouder.commands import AlignBlockWithSegmentCommand
from anaouder.interfaces import DocumentInterface
from anaouder.lang import prepTextForAlignment
from anaouder.services.logger import logger
from anaouder.services.media_player_controller import MediaPlayerController
from anaouder.services.task import TaskQueue, TaskWorker
from anaouder.transcriber import TranscriptionService, VoskFileTranscriptionWorker
from anaouder.ui.dialogs import ProgressDialog
from anaouder.utils import PUNCTUATION, filter_out_chars

SPLIT_TOKEN = "|"


class SmartSplitError(Exception):
    """Custom exception for errors during smart splitting"""

    pass


def smart_split_text(text: str, position: int, vosk_tokens: list) -> tuple:
    """
    Split a text at a given character position
    while trying to keep it aligned with timecoded tokens

    Args:
        text: text to be splitted
        position: character position where to split
        vosk_tokens: list of timecoded tokens of the format
            (start_time, end_time, word, confidence, language)

    Returns:
        A 2-tuple consisting of the left part and the right part,
        where each part is a list of timecoded tokens
    """

    if not can_smart_split(text, vosk_tokens):
        # Will call prepare_sentence, like align_text_with_vosk_token
        # We could take advantage of that to avoid redundant calls
        raise SmartSplitError("CER is too high")

    left_text = text[:position].rstrip()
    right_text = text[position:].lstrip()

    result = align_text_with_vosk_tokens(
        f"{left_text} {SPLIT_TOKEN} {right_text}", vosk_tokens
    )

    # Find index of split token
    i = 0
    for t, _ in result:
        if t == SPLIT_TOKEN:
            break
        i += 1

    if i == 0:
        return [], [vosk_tokens[0][0], vosk_tokens[-1][1]]
    if i == len(result) - 1:
        return [vosk_tokens[0][0], vosk_tokens[-1][1]], []

    # Check if neighbours are valid
    prev_token = None
    r = 1
    while i - r >= 0:
        if result[i - r][1] == None:
            r += 1
        else:
            prev_token = result[i - r][1]
            break
    if prev_token == None:
        prev_token = (vosk_tokens[0][2], vosk_tokens[0][0], vosk_tokens[0][1])

    next_token = None
    r = 1
    while i + r < len(result):
        if result[i + r][1] == None:
            r += 1
        else:
            next_token = result[i + r][1]
            break
    if next_token == None:
        next_token = (vosk_tokens[-1][2], vosk_tokens[-1][0], vosk_tokens[-1][1])

    left_seg = [vosk_tokens[0][0], prev_token[2]]
    right_seg = [next_token[1], vosk_tokens[-1][1]]
    return left_seg, right_seg


def smart_split_time(text: str, timepos: float, vosk_tokens: list) -> tuple:
    """
    Split a text based on a gap index from a hypotheses token list

    Args:
        text: text to be splitted
        idx: gap index between two tokens
        vosk_tokens: list of timecoded tokens of the format
            (start_time, end_time, word, confidence, language)

    Returns:
        A 2-tuple consisting of the left text and the right text
    """
    if not can_smart_split(text, vosk_tokens):
        # Will call prepare_sentence.
        # We could take advantage of that to avoid redundant calls
        raise SmartSplitError("CER is too high")

    # Find the best location to split the transcribed sentence
    idx = 0
    for t_start, t_end, word, _, _ in vosk_tokens:
        if timepos < t_start + (t_end - t_start) * 0.5:
            break
        idx += 1

    # Add a split token in the list of transcribed tokens
    left_tokens = vosk_tokens[:idx]
    right_tokens = vosk_tokens[idx:]
    left_hyp = " ".join([t[2] for t in left_tokens])
    right_hyp = " ".join([t[2] for t in right_tokens])

    words = text.split()

    # Iterate to find the best sentence split candidate
    best_idx, best_score = -1, inf
    for i in range(len(words) + 1):
        left_split = prep_sentence(" ".join(words[:i]))
        right_split = prep_sentence(" ".join(words[i:]))
        score = 0.5 * jiwer.cer(left_hyp, left_split) + 0.5 * jiwer.cer(
            right_hyp, right_split
        )
        if score < best_score:
            best_idx = i
            best_score = score

    return (" ".join(words[:best_idx]), " ".join(words[best_idx:]))


def can_smart_split(text: str, vosk_tokens: list):
    """
    Test if this sentence is similar enough
    to the decoded transcription (list of vosk tokens) to be aligned
    """
    # Simplify text representation
    gt = prep_sentence(text)
    hyp = prep_sentence(" ".join([t[2] for t in vosk_tokens]))
    cer = jiwer.cer(gt, hyp)
    return cer < 0.5


def prep_sentence(sentence: str, remove_spaces=True) -> str:
    """
    Return a simplified representation of the given sentence,
    for more better alignment
    """
    sentence = sentence.lower()
    sentence = sentence.replace("\n", " ")
    sentence = re.sub(r"{.+?}", "", sentence)  # Ignore metadata
    sentence = re.sub(r"<[A-Z\']+?>", "¤", sentence)  # Replace special tokens
    sentence = sentence.replace("*", "")
    sentence = sentence.replace(
        "-", " "
    )  # Needed for Breton, but how does it impact other languages?
    sentence = sentence.replace(".", " ")
    sentence = filter_out_chars(sentence, PUNCTUATION)

    normalized = prepTextForAlignment(sentence)

    if remove_spaces:
        sentence = normalized.replace(" ", "")

    return sentence


def align_text_with_vosk_tokens(
    text: str, vosk_tokens: list, cancel_check=None
) -> list:
    """
    Args:
        text: ground truth text
        vosk_tokens: list of tuples, where each tuple represents a single token
            with the format (start_time, end_time, word, confidence, language)

    Returns:
        list of tuple, where each tuple represent an alignment candidate
            with the format (ground_truth_word, (hyp_word, start, end))
    """
    # Simplify text representation
    gt_words = prep_sentence(text, remove_spaces=False).split()

    hyp_words = [(prepTextForAlignment(t[2]), t[0], t[1]) for t in vosk_tokens]

    n, m = len(gt_words), len(hyp_words)
    dp = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0

    del_cost = 2.0
    ins_cost = 1.0

    # Fill the matrix using Levenshtein distance
    for i in range(n + 1):
        if cancel_check and cancel_check():
            return []

        for j in range(m + 1):
            if i > 0 and j > 0:
                if gt_words[i - 1] == hyp_words[j - 1][0]:
                    cost = 0
                else:
                    cost = jiwer.cer(gt_words[i - 1], hyp_words[j - 1][0])
                dp[i][j] = min(dp[i][j], dp[i - 1][j - 1] + cost)
            if i > 0:
                dp[i][j] = min(dp[i][j], dp[i - 1][j] + del_cost)  # deletion
            if j > 0:
                dp[i][j] = min(dp[i][j], dp[i][j - 1] + ins_cost)  # insertion
    # _print_matrix(dp)

    if cancel_check and cancel_check():
        return []

    # Backtrack to find alignment
    alignment = []
    i, j = n, m
    while i > 0 or j > 0:
        if cancel_check and cancel_check():
            return []

        if i > 0 and j > 0:  # Add bounds check
            sub_cost = jiwer.cer(gt_words[i - 1], hyp_words[j - 1][0])
            if dp[i][j] == dp[i - 1][j - 1] + sub_cost:
                alignment.append((gt_words[i - 1], hyp_words[j - 1]))
                i, j = i - 1, j - 1
                continue

        if i > 0 and dp[i][j] == dp[i - 1][j] + del_cost:
            alignment.append((gt_words[i - 1], None))
            i -= 1
        elif j > 0:  # Changed from else to elif
            alignment.append((None, hyp_words[j - 1]))
            j -= 1

    return list(reversed(alignment))


SENTENCE_SEPARATOR = "||"


def _group_to_segment(group: list) -> list | None:
    """
    Return the [start, end] time span of a sentence, given its aligned words,
    or None if none of its words could be aligned to a token.
    """
    tokens = [hyp for _, hyp in group if hyp is not None]
    if not tokens:
        return None
    return [tokens[0][1], tokens[-1][2]]


def segments_from_alignment(alignment: list) -> list:
    """
    Split the result of `align_text_with_vosk_tokens` into sentences.

    The aligned text must be of the form "|| s1 || s2 || ... || sN ||".
    Returns exactly one entry per sentence: a [start, end] list,
    or None when the sentence couldn't be aligned (including sentences
    that normalize to no words at all), so that indices stay in sync
    with the list of sentences.
    """
    segments = []
    group = None  # None until the first separator is met
    for gt_word, hyp in alignment:
        if gt_word is None:
            # Inserted token, not part of any sentence
            continue
        if gt_word == SENTENCE_SEPARATOR:
            if group is not None:
                segments.append(_group_to_segment(group))
            group = []
            continue
        if group is not None:
            group.append((gt_word, hyp))
    return segments



class TextAlignerWorker(TaskWorker):
    segments_found = Signal(list)

    def __init__(self, parent, blocks: list[QTextBlock], tokens: list):
        super().__init__(parent)
        self.sentences = [block.text() for block in blocks]
        self.tokens = tokens[:]  # Make a copy to be thread safe
        self.segments = []

        assert self.sentences
        assert self.tokens


    def run(self):
        QThread.currentThread().setPriority(QThread.Priority.HighPriority)

        try:
            text = f" {SENTENCE_SEPARATOR} ".join(self.sentences)
            text = f"{SENTENCE_SEPARATOR} {text} {SENTENCE_SEPARATOR}"
            alignment = align_text_with_vosk_tokens(
                text, self.tokens, cancel_check=lambda: self._must_stop
            )

            if self._must_stop:
                self.stopped.emit()
                return

            segments = segments_from_alignment(alignment)
            if len(segments) != len(self.sentences):
                logger.error(
                    f"Alignment returned {len(segments)} segments "
                    f"for {len(self.sentences)} sentences"
                )
                self.failed.emit()
                return

            self.segments = segments
            self.segments_found.emit(segments)
            self.completed.emit()

        except Exception as e:
            logger.error(f"Alignment error: {e}")
            self.failed.emit()



class TextAligner(QObject):
    def __init__(
        self,
        parent,
        document_controller: DocumentInterface,
        media_controller: MediaPlayerController,
        recognizer: TranscriptionService,
    ):
        super().__init__(parent)

        self.parent_window = parent
        self.document_controller = document_controller
        self.media_controller = media_controller
        self.undo_stack = document_controller.undo_stack
        self.recognizer = recognizer
        self.alignment_thread = None
        self.progress_dialog: ProgressDialog | None = None
        self.progress_bar = None
        # (signal, slot) pairs connected on the shared recognizer
        self._recognizer_connections: list = []


    def _connect_recognizer(self, signal, slot) -> None:
        signal.connect(slot)
        self._recognizer_connections.append((signal, slot))


    def _disconnect_recognizer(self) -> None:
        """Remove every connection made on the recognizer by `autoAlign`"""
        for signal, slot in self._recognizer_connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass
        self._recognizer_connections.clear()


    def _on_hidden_transcription_progress(self, time_s: float) -> None:
        if self.progress_dialog is None:
            return
        duration = self.media_controller.getDuration()
        if duration:
            self.progress_dialog.progress_bar.setValue(round(100 * time_s / duration))


    def _on_operation_stopped(self) -> None:
        if self.progress_dialog:
            self.progress_dialog.close()


    def autoAlign(self) -> None:
        """
        Dependecies:
            media_path
            progress_bar
            document_controller
        """
        logger.debug("TextAligner.autoAlign()")
        self._disconnect_recognizer()

        media_path = self.document_controller.media_path

        if media_path is None:
            logger.error("No media file detected")
            return

        # Check if there is a cached transcription for this media
        # or if we need to transcribe the whole file first
        media_metadata = cache.get_media_metadata(media_path)
        is_missing_transcription = not media_metadata.get(
            "transcription_completed", False
        )

        alignment_args = self.document_controller.get_selected_blocks_and_time_range()

        if alignment_args is None:
            return

        blocks, time_range = alignment_args

        self.progress_dialog = ProgressDialog(self.parent_window)

        # tasks: List[TaskWorker] = []

        # if is_missing_transcription:
        #     tasks.append(VoskFileTranscriptionWorker(self, media_path, 0.0, ))

        # tokens = self.document_controller.getTranscriptionForSegment(time_range[0], time_range[1])
        # tasks.insert(0, TextAlignerThread(self, blocks, tokens))

        # self._queue = TaskQueue(tasks, parent=self)

        def start_alignment():
            # One-shot: never re-run on a later, unrelated transcription
            self._disconnect_recognizer()

            # Set the progress bar in indeterminate mode
            self.progress_dialog.progress_bar.setRange(0, 0)
            self.progress_dialog.setValue(0)
            self.progress_dialog.cancelled.connect(on_alignment_canceled)
            self.progress_dialog.setMessage(self.tr("Aligning text with speech..."))

            tokens = self.document_controller.getTranscriptionForSegment(
                time_range[0], time_range[1]
            )

            self.alignment_thread = TextAlignerWorker(self, blocks, tokens)
            self.alignment_thread.segments_found.connect(on_alignment_complete)
            self.alignment_thread.stopped.connect(self._on_operation_stopped)
            self.alignment_thread.failed.connect(self._on_operation_stopped)
            self.alignment_thread.start()

        def on_alignment_canceled():
            if self.alignment_thread is not None and self.alignment_thread.isRunning():
                self.alignment_thread.stop()

        def on_alignment_complete(segments):
            if len(segments) != len(blocks):
                logger.error(
                    f"Got {len(segments)} segments for {len(blocks)} blocks, "
                    "aborting alignment"
                )
                segments = []
            self.undo_stack.beginMacro("Auto alignment")
            for block, segment in zip(blocks, segments):
                if segment is None:
                    continue
                self.undo_stack.push(
                    AlignBlockWithSegmentCommand(self.document_controller, block, segment)
                )
            self.undo_stack.endMacro()

            # Close loading dialog
            if self.progress_dialog is not None:
                self.progress_dialog.close()

            # Clean up thread
            if self.alignment_thread is not None:
                self.alignment_thread.wait()
                self.alignment_thread.deleteLater()
                self.alignment_thread = None

        if is_missing_transcription:
            # Start with hidden transcription first
            self.progress_dialog.progress_bar.setRange(0, 100)
            self.progress_dialog.cancelled.connect(self.recognizer.stop)
            self.progress_dialog.cancelled.connect(self._disconnect_recognizer)
            self.progress_dialog.cancelled.connect(self._on_operation_stopped)
            self.progress_dialog.setMessage(self.tr("Hidden transcription..."))

            # The recognizer is shared with the rest of the app: keep track of
            # these connections so they can be removed once the hidden
            # transcription is over (or cancelled, in which case
            # `finished` is never emitted)
            self._connect_recognizer(
                self.recognizer.progress, self._on_hidden_transcription_progress
            )
            self._connect_recognizer(self.recognizer.finished, start_alignment)

            start_time = media_metadata.get("transcription_progress", 0.0)
            self.recognizer.transcribeFile(str(media_path), start_time, is_hidden=True)
        else:
            start_alignment()

        # Show loading dialog
        self.progress_dialog.exec()


def _print_matrix(matrix):
    # 2D matrix
    for row in matrix:
        r = [f"{val:.2f}" for val in row]
        print(f"[{' '.join(r)}]")


def print_alignment(alignment: list) -> None:
    top_line = []
    bottom_line = []
    for gt_word, hyp in alignment:
        gt_word = gt_word if gt_word else "*"
        hyp = hyp[0] if hyp else "*"
        max_len = max(len(gt_word), len(hyp))
        top_line.append(gt_word.ljust(max_len))
        bottom_line.append(hyp.ljust(max_len))

    print("--------")
    print(" ".join(top_line))
    print(" ".join(bottom_line))
