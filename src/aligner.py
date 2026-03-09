"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

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


from typing import List
import logging
import re
import jiwer
from math import inf

from PySide6.QtCore import QRunnable, Signal, QObject, QThread
from PySide6.QtGui import QTextBlock

from ui.progess_dialog import ProgressDialog
from services.media_player_controller import MediaPlayerController
from transcriber import TranscriptionService
from interfaces import DocumentInterface
from commands import AlignBlockWithSegment
from cache_system import cache
from lang import prepTextForAlignment
from utils import PUNCTUATION



log = logging.getLogger(__name__)



SPLIT_TOKEN = '|'



class SmartSplitError(Exception):
    """Custom exception for errors during smart splitting
    """
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

    result = align_text_with_vosk_tokens(' '.join([left_text, SPLIT_TOKEN, right_text]), vosk_tokens)
    
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
    while i-r >= 0:
        if result[i-r][1] == None:
            r += 1
        else:
            prev_token = result[i-r][1]
            break
    if prev_token == None:
        prev_token = (vosk_tokens[0][2], vosk_tokens[0][0], vosk_tokens[0][1])
    
    next_token = None
    r = 1
    while i+r < len(result):
        if result[i+r][1] == None:
            r += 1
        else:
            next_token = result[i+r][1]
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
    left_hyp = ' '.join([ t[2] for t in left_tokens ])
    right_hyp = ' '.join([ t[2] for t in right_tokens ])

    words = text.split()

    # Iterate to find the best sentence split candidate
    best_idx, best_score = -1, inf
    for i in range(len(words) + 1):
        left_split = prep_sentence(' '.join(words[:i]))
        right_split = prep_sentence(' '.join(words[i:]))
        score = (
            0.5 * jiwer.cer(left_hyp, left_split)
            + 0.5 * jiwer.cer(right_hyp, right_split)
        )
        if score < best_score:
            best_idx = i
            best_score = score

    return (' '.join(words[:best_idx]), ' '.join(words[best_idx:]))


def can_smart_split(text: str, vosk_tokens: list):
    # Simplify text representation
    gt = prep_sentence(text)
    hyp = prep_sentence(' '.join([t[2] for t in vosk_tokens]))
    cer = jiwer.cer(gt, hyp)
    print(f"{cer=}")
    return cer < 0.5


def prep_sentence(sentence: str, remove_spaces=True) -> str:
    """
    Return a simplified representation of the given sentence,
    for more better alignment
    """
    sentence = sentence.lower()
    sentence = sentence.replace('\n', ' ')
    sentence = re.sub(r"{.+?}", '', sentence)        # Ignore metadata
    sentence = re.sub(r"<[A-Z\']+?>", '¤', sentence) # Replace special tokens
    sentence = sentence.replace('*', '')
    sentence = sentence.replace('-', ' ')            # Needed for Breton, but how does it impact other languages?
    sentence = sentence.replace('.', ' ')
    sentence = filter_out_chars(sentence, PUNCTUATION)

    normalized = prepTextForAlignment(sentence)

    if remove_spaces:
        sentence = normalized.replace(' ', '')
        
    return sentence


def _print_matrix(matrix):
    # 2D matrix
    for row in matrix:
        r = [ f"{val:.2f}" for val in row ]
        print(f"[{' '.join(r)}]")


def filter_out_chars(text: str, chars: str) -> str:
    """Remove given characters from a string"""

    filtered_text = ""
    for l in text:
        if not l in chars: filtered_text += l
    return filtered_text



class TextAlignerThread(QThread):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, blocks: List[QTextBlock], tokens: list, parent=None):
        super().__init__(parent)
        self.sentences = [block.text() for block in blocks]
        self.tokens = tokens
        self.segments = []

        self._must_stop = False
    
    def cancel(self):
        self._must_stop = True

    def run(self):
        QThread.currentThread().setPriority(QThread.Priority.HighPriority)

        try:
            text = "|| " + " || ".join(self.sentences) + " || "
            
            alignment = align_text_with_vosk_tokens(text, self.tokens, cancel_check=lambda: self._must_stop)

            if self._must_stop:
                return

            # Separating into segments
            segments = []
            segment_tokens = []
            for al in alignment:
                if al[0] is None:
                    continue
                if al[0] == "||":
                    # print("||")
                    if segment_tokens:
                        first_idx = 0
                        last_idx = len(segment_tokens) - 1
                        first_token = segment_tokens[first_idx][1]
                        last_token = segment_tokens[last_idx][1]
                        # Skip first tokens if they align to None
                        while (first_token is None) and (first_idx < last_idx):
                            first_idx += 1
                            first_token = segment_tokens[first_idx][1]
                        # Skip last tokens if they align to None
                        while (last_token is None) and (first_idx < last_idx):
                            last_idx -= 1
                            last_token = segment_tokens[last_idx][1]

                        if not (first_token or last_token):
                            segments.append(None)
                            segment_tokens.clear()
                            continue
                        
                        if first_token:
                            segment_start = first_token[1]
                        else:
                            segment_start = last_token[1]
                        
                        if last_token:
                            segment_end = last_token[2]
                        else:
                            segment_end = first_token[2]
                        
                        segments.append([segment_start, segment_end])
                        segment_tokens.clear()
                    continue
                segment_tokens.append(al)

            self.segments = segments
            self.finished.emit(segments)
        
        except Exception as e:
            log.error(f"Alignment error: {e}")
            self.error.emit(str(e))


def align_text_with_vosk_tokens(text: str, vosk_tokens: list, cancel_check=None) -> list:
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

    hyp_words = [ (prepTextForAlignment(t[2]), t[0], t[1]) for t in vosk_tokens]

    n, m = len(gt_words), len(hyp_words)
    dp = [[float('inf')] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0

    del_cost = 2.0
    ins_cost = 1.0
    
    # Fill the matrix using Levenshtein distance
    for i in range(n + 1):
        if cancel_check and cancel_check():
            return []
    
        for j in range(m + 1):
            if i > 0 and j > 0:
                if gt_words[i-1] == hyp_words[j-1][0]:
                    cost = 0 
                else:
                    cost = jiwer.cer(gt_words[i-1], hyp_words[j-1][0])
                dp[i][j] = min(dp[i][j], dp[i-1][j-1] + cost)
            if i > 0:
                dp[i][j] = min(dp[i][j], dp[i-1][j] + del_cost)  # deletion
            if j > 0:
                dp[i][j] = min(dp[i][j], dp[i][j-1] + ins_cost)  # insertion
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
            sub_cost = jiwer.cer(gt_words[i-1], hyp_words[j-1][0])
            if dp[i][j] == dp[i-1][j-1] + sub_cost:
                alignment.append((gt_words[i-1], hyp_words[j-1]))
                i, j = i-1, j-1
                continue
    
        if i > 0 and dp[i][j] == dp[i-1][j] + del_cost:
            alignment.append((gt_words[i-1], None))
            i -= 1
        elif j > 0:  # Changed from else to elif
            alignment.append((None, hyp_words[j-1]))
            j -= 1
    
    return list(reversed(alignment))



class TextAligner(QObject):
    error = Signal(str)

    def __init__(
            self,
            parent,
            document_controller: DocumentInterface,
            media_controller: MediaPlayerController,
            recognizer: TranscriptionService
        ):
        self.parent_window = parent
        self.document_controller = document_controller
        self.media_controller = media_controller
        self.undo_stack = document_controller.undo_stack
        self.recognizer = recognizer
        self.alignment_thread = None
        self.progress_bar = None


    def autoAlign(self) -> None:
        """
        media_path
        progress_bar
        document_controller
        """
        log.debug("autoAlign()")

        media_path = self.document_controller.media_path

        if media_path is None:
            return
        
        # Check if there is a cached transcription for this media
        is_missing_transcription = False
        media_metadata = cache.get_media_metadata(media_path)
        if not media_metadata.get("transcription_completed", False):
            # We need to transcribe the whole file first
            is_missing_transcription = True

        alignment_data = self.document_controller.getSelectedBlocksAndTimeRange()
        if alignment_data is None:
            return
        blocks, time_range = alignment_data

        self.loading_dialog = ProgressDialog(self.parent_window)
        
        def start_alignment():
            # Set the progress bar in indeterminate mode
            self.loading_dialog.progress_bar.setRange(0, 0)
            self.loading_dialog.progress_bar.setValue(0)
            self.loading_dialog.cancelled.connect(on_alignment_canceled)
            self.loading_dialog.setMessage(self.tr("Aligning text with speech..."))

            tokens = self.document_controller.getTranscriptionForSegment(time_range[0], time_range[1])

            self.alignment_thread = TextAlignerThread(blocks, tokens, self.parent_window)
            self.alignment_thread.finished.connect(on_alignment_complete)
            self.alignment_thread.error.connect(self.error.emit)

            self.alignment_thread.start()

        def on_alignment_canceled():
            if self.alignment_thread is not None and self.alignment_thread.isRunning():
                self.alignment_thread.cancel()

        def on_alignment_complete(segments):
            self.undo_stack.beginMacro("Auto alignment")
            for i, segment in enumerate(segments):
                if segment is None:
                    continue
                self.undo_stack.push(
                    AlignBlockWithSegment(self.document_controller, blocks[i], segment)
                )
            self.undo_stack.endMacro()

            # Close loading dialog
            if self.loading_dialog is not None:
                self.loading_dialog.close()
            
            # Clean up thread
            if self.alignment_thread is not None:
                self.alignment_thread.wait()
                self.alignment_thread.deleteLater()
                self.alignment_thread = None

        if is_missing_transcription:
            # Start with hidden transcription first
            self.loading_dialog.progress_bar.setRange(0, 100)
            self.loading_dialog.cancelled.connect(self.recognizer.stop)
            self.loading_dialog.setMessage(self.tr("Hidden transcription..."))

            self.recognizer.progress.connect(
                lambda time_s:
                self.loading_dialog.progress_bar.setValue(
                    round(100 * time_s / self.media_controller.getDuration())
                )
            )
            self.recognizer.finished.connect(start_alignment)

            start_time = media_metadata.get("transcription_progress", 0.0)
            self.recognizer.transcribeFile(str(media_path), start_time, is_hidden=True)
        else:
            start_alignment()

        # Show loading dialog
        self.loading_dialog.exec()