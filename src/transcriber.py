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


from typing import Optional
from pathlib import Path
import logging
import locale
import platform
import subprocess
import json

from vosk import KaldiRecognizer
from PySide6.QtCore import (
    QObject, QThread,
    Signal, Slot,
)

from ostilhou.asr.models import load_model

from src.cache_system import cache
from src.interfaces import Segment, SegmentId
from src.lang import getModelPath, getCurrentLanguage



log = logging.getLogger(__name__)



def commit_transcription_to_cache(media_path: str, tokens: list) -> None:
    """ Backup transcription in cache """

    if not tokens:
        return

    # Simplify tokens list
    tokens = [
        (
            round(t["start"], 3),
            round(t["end"], 3),
            t["word"],
            round(t["conf"], 3),
            t["lang"]
        ) for t in tokens
    ]

    # Update backend transcription with new tokens
    old_tokens = cache.get_media_transcription(Path(media_path))
    if old_tokens is None:
        old_tokens = []
    updated_tokens = []
    segment_start = tokens[0][0]
    segment_end = tokens[-1][1]
    idx = 0
    if not old_tokens or segment_start >= old_tokens[-1][1]:
        # Add tokens at the end
        updated_tokens = old_tokens + tokens
    else:
        for tok in old_tokens:
            # Skip preceding tokens
            if tok[1] > segment_start:
                break
            updated_tokens.append(tok)
            idx += 1
        for tok in tokens:
            updated_tokens.append(tok)
        while idx < len(old_tokens) and old_tokens[idx][0] < segment_end:
            # Go over old tokens in the same location
            idx += 1
        for tok in old_tokens[idx:]:
            # Add later tokens
            updated_tokens.append(tok)
    
    # Update transcription in cache
    cache.set_media_transcription(Path(media_path), updated_tokens)

    # Update transcription progress metadata
    old_progress = cache.get_media_metadata(Path(media_path)).get("transcription_progress", 0.0)
    cache.update_media_metadata(
        Path(media_path),
        { "transcription_progress": max(0.0, old_progress) }
    )



class RecognizerWorker(QObject):
    # Signals
    segment_transcribed = Signal(str, list, int) # (re-)transcribe a pre-defined segment
    new_segment_transcribed = Signal(str, list) # Create a new utterance with transcription
    progress = Signal(float)    # In seconds since the beginning of the audio file
    message = Signal(str)   # Sends a message to be displayed in the status bar
    end_of_file = Signal()  # Whole file transcription is completed
    finished = Signal()     # Used to toggle up the transcription button

    # Constants
    SAMPLE_RATE = 16000


    def __init__(self):
        """This worker should only be created once"""

        super().__init__()
        self.loaded_model = None
        self.loaded_model_path = None
        self.recognizer = None
        self._must_stop = False
        # Stupid hack with locale to avoid commas in vosk json string
        if platform.system() == "Linux":
            locale.setlocale(locale.LC_ALL, ("C", "UTF-8"))
        else:
            locale.setlocale(locale.LC_ALL, ("en_us", "UTF-8")) # locale en_US works on macOS


    def set_model_path(self, model_name) -> None:
        model_path = getModelPath(model_name)
        if model_path != self.loaded_model_path:
            self.message.emit(f"Loading {model_name}")
            self.loaded_model = load_model(model_path)
            self.loaded_model_path = model_path
            self.recognizer = KaldiRecognizer(self.loaded_model, self.SAMPLE_RATE)
            self.recognizer.SetWords(True)


    def transcribe_file(self, media_path: str, start_time: float, is_hidden=False) -> None:
        """ 
        Transcribe a whole audio file by streaming from ffmpeg to Vosk.
        Emit a signal, passing a list of tokens, for each recognized utterance.
        
        Args:
            file_path (str): Path to the audio file
            start_time (float): Start time in seconds
        """
        log.debug(f"transcribeFile({media_path=}, {start_time=}, {is_hidden=})")
        current_language = getCurrentLanguage()

        self.message.emit(self.tr("Transcribing whole file") + '...')

        # It's not enough to "reset" the recognizer, the timecodes would keep incrementing
        # so we need to create a new instance
        self.recognizer = KaldiRecognizer(self.loaded_model, self.SAMPLE_RATE)
        self.recognizer.SetWords(True)

        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",     # Reduce ffmpeg output to bare minimum
            "-i", media_path,
            "-ss", str(start_time),                   
            "-ar", str(self.SAMPLE_RATE), "-ac", "1", # 16kHz sample rate, single channel
            "-f", "s16le",                            # 16-bit signed little-endian PCM
            "-",                                      # Output to stdout
        ]

        subprocess_args = {}
        if platform.system() == "Windows":
            # This flag tells Windows: "Don't create a console window for this process"
            subprocess_args["creationflags"] = subprocess.CREATE_NO_WINDOW
        
        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **subprocess_args
            )
            
            # Process the audio stream in chunks
            self._must_stop = False
            chunk_size = 4000
            cumul_samples = 0
            while not self._must_stop:
                if process.stdout is None:
                    break

                data = process.stdout.read(chunk_size)

                if len(data) == 0:
                    break

                cumul_samples += len(data) // 2 # 2 bytes per sample
                self.progress.emit(start_time + (cumul_samples / self.SAMPLE_RATE))
                    
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    if "result" in result:
                        tokens = result["result"]
                        for tok in tokens:
                            tok["start"] += start_time
                            tok["end"] += start_time
                            tok["lang"] = current_language
                        if not self._must_stop:
                            commit_transcription_to_cache(media_path, tokens)
                            if not is_hidden:
                                text = ' '.join([tok["word"] for tok in tokens])
                                segment = [tokens[0]["start"], tokens[-1]["end"]]
                                self.new_segment_transcribed.emit(text, segment)
            
            if not self._must_stop:
                result = json.loads(self.recognizer.FinalResult())
                if "result" in result:
                    tokens = result["result"]
                    for tok in tokens:
                            tok["start"] += start_time
                            tok["end"] += start_time
                            tok["lang"] = current_language
                    
                    commit_transcription_to_cache(media_path, tokens)
                    if not is_hidden:
                        text = ' '.join([tok["word"] for tok in tokens])
                        segment = [tokens[0]["start"], tokens[-1]["end"]]
                        self.new_segment_transcribed.emit(text, segment)
            
                # The 'finished' signal should be sent only if
                # the recognizer wasn't interrupted by the user
                self.finished.emit()
                self.end_of_file.emit()
        
        except Exception as e:
            log.error(e)
            self.message.emit(self.tr("Error during transcription: {error}").format(error=e))

        finally:
            if process:
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

                if process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


    def transcribeSegments(self, file_path: str, segments: list):
        """
        Transcribe a list of pre-defined segments from an audio file.

        Args:
            file_path (str): Path to the audio file
            segments (list): List of tuples (segment_id, start_time, end_time)
        """

        current_language = getCurrentLanguage()

        self._must_stop = False
        for i, (seg_id, start, end) in enumerate(segments):
            self.message.emit(
                self.tr("Transcribing") + f" {i+1}/{len(segments)}"
            )
            tokens = self._transcribeSegment(file_path, start, end-start, current_language)
            if self._must_stop:
                break
            
            # Update cache with this segment's new transcription
            commit_transcription_to_cache(file_path, tokens)

            text = ' '.join([tok["word"] for tok in tokens])
            self.segment_transcribed.emit(text, [start, end], seg_id)
        if not self._must_stop:
            # The 'finished' signal should be sent only when
            # the recognizer wasn't interrupted
            self.finished.emit()


    def _transcribeSegment(
            self,
            file_path: str,
            start_time_seconds: float, 
            duration_seconds: float,
            lang: str,
        ) -> list:
        """ 
        Transcribe a single segment of an audio file by streaming from ffmpeg to Vosk.
        
        Args:
            input_file: Path to the audio file
            start_time: Start time in seconds
            duration: Duration of segment in seconds
            
        Returns:
            List of vosk tokens
        """
        
        if self.recognizer is None:
            return []

        self.recognizer.Reset()    # We won't be using the timecodes here anyway
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",     # Reduce ffmpeg output to bare minimum
            "-i", file_path,
            "-ss", str(start_time_seconds),
            "-t", str(duration_seconds),
            "-ar", str(self.SAMPLE_RATE), "-ac", "1", # 16kHz sample rate, single channel
            "-f", "s16le",                            # 16-bit signed little-endian PCM
            "-",                                      # Output to stdout
        ]

        subprocess_args = {}
        if platform.system() == "Windows":
            # This flag tells Windows: "Don't create a console window for this process"
            # It is only available in Python 3.7+ on Windows
            subprocess_args["creationflags"] = subprocess.CREATE_NO_WINDOW
        
        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **subprocess_args
            )
            
            # Process the audio stream in chunks
            chunk_size = 4000
            tokens = []
            self._must_stop = False
            while not self._must_stop:
                data = process.stdout.read(chunk_size)
                if len(data) == 0:
                    break
                    
                if self.recognizer.AcceptWaveform(data):
                    tokens.extend(json.loads(self.recognizer.Result())["result"])
            
            if not self._must_stop:
                tokens.extend(json.loads(self.recognizer.FinalResult())["result"])
        
        except Exception as e:
            self.message.emit(f"Error during transcription: {e}")

        finally:
            if process:
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

                if process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        
        for tok in tokens:
            tok["start"] += start_time_seconds
            tok["end"] += start_time_seconds
            tok["lang"] = lang
        return tokens
    

    def stop(self) -> None:
        """ Stop the current transcription """
        self._must_stop = True



class TranscriptionService(QObject):
    """
    Manages the RecognizerWorker and its thread.
    This is the main interface for the MainWindow.
    """
    # Expose signals from the worker
    segment_transcribed = Signal(str, list, int)
    new_segment_transcribed = Signal(str, list)
    progress = Signal(float)
    message = Signal(str)
    end_of_file = Signal()
    finished = Signal()

    # Add signals to trigger worker methods
    start_file_transcription = Signal(str, float, bool)
    start_segments_transcription = Signal(str, list)
    set_model_path = Signal(str)


    def __init__(self, parent=None):
        super().__init__(parent)
        self._recognizer_worker = RecognizerWorker()
        self._thread = QThread()
        self._recognizer_worker.moveToThread(self._thread)

        # Connect worker signals to the service's signals
        self._recognizer_worker.segment_transcribed.connect(self.segment_transcribed)
        self._recognizer_worker.new_segment_transcribed.connect(self.new_segment_transcribed)
        self._recognizer_worker.progress.connect(self.progress)
        self._recognizer_worker.end_of_file.connect(self.end_of_file)
        self._recognizer_worker.finished.connect(self.finished)
        self._recognizer_worker.message.connect(self.message)

        # Connect service's trigger signals to worker's slots
        self.start_file_transcription.connect(self._recognizer_worker.transcribe_file)
        self.start_segments_transcription.connect(self._recognizer_worker.transcribeSegments)
        self.set_model_path.connect(self._recognizer_worker.set_model_path)

        self._thread.start()


    @Slot(str)
    def setModelPath(self, model_name) -> None:
        self.set_model_path.emit(model_name)


    @Slot(str, float, bool)
    def transcribeFile(
        self,
        file_path: str,
        start_time: float,
        is_hidden: Optional[bool] = None
    ) -> None:
        self.start_file_transcription.emit(file_path, start_time, is_hidden)


    @Slot(str, list)
    def transcribeSegments(self, file_path: str, segments: list):
        self.start_segments_transcription.emit(file_path, segments)


    def stop(self):
        self._recognizer_worker.stop()


    def cleanup(self):
        if self._thread.isRunning():
            self._recognizer_worker.stop()
        self._recognizer_worker.deleteLater()
        
        self._thread.quit()
        self._thread.wait(2000) # 2 second timeout
        if self._thread.isRunning():
            self._thread.terminate()
        self._thread.deleteLater()