import locale
import platform
import subprocess
import json

from vosk import KaldiRecognizer
from PySide6.QtCore import (
    QObject,
    Signal, Slot,
    QCoreApplication
)

from ostilhou.asr.models import load_model

from src.lang import postProcessText, getModelPath



class RecognizerWorker(QObject):
    """This worker should needs only to be created once"""

    SAMPLE_RATE = 16000

    segment_transcribed = Signal(str, float, float, int, int) # (re-)transcribe a pre-defined segment
    new_segment_transcribed = Signal(str, list) # Create a new utterance with transcription
    progress = Signal(float)
    message = Signal(str)
    finished = Signal()


    def __init__(self):
        super().__init__()
        self.loaded_model = None
        self.loaded_model_path = None
        self.recognizer = None
        self.must_stop = False
        # Stupid hack with locale to avoid commas in vosk json string
        if platform.system() == "Linux":
            locale.setlocale(locale.LC_ALL, ("C", "UTF-8"))
        else:
            locale.setlocale(locale.LC_ALL, ("en_us", "UTF-8")) # locale en_US works on macOS


    @Slot(str)
    def setModelPath(self, model_name):
        model_path = getModelPath(model_name)
        if model_path != self.loaded_model_path:
            self.message.emit(f"Loading {model_name}")
            self.loaded_model = load_model(model_path)
            self.loaded_model_path = model_path
            self.recognizer = KaldiRecognizer(self.loaded_model, 16000)
            self.recognizer.SetWords(True)


    @Slot()
    def transcribeFile(self, file_path: str):
        def parse_vosk_result(result):
            text = ' '.join([vosk_token['word'] for vosk_token in result])
            segment = [result[0]['start'], result[-1]['end']]
            return postProcessText(text), segment
        
        self.message.emit(f"Transcribing...")

        # It's not enough to "reset" the recognizer, lest the timecodes keep incrementing
        self.recognizer = KaldiRecognizer(self.loaded_model, self.SAMPLE_RATE)
        self.recognizer.SetWords(True)
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",     # Reduce ffmpeg output to bare minimum
            "-i", file_path,
            "-ar", str(self.SAMPLE_RATE), "-ac", "1", # 16kHz sample rate, single channel
            "-f", "s16le",                            # 16-bit signed little-endian PCM
            "-",                                      # Output to stdout
        ]
        
        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Process the audio stream in chunks
            self.must_stop = False
            chunk_size = 4000
            while not self.must_stop:
                data = process.stdout.read(chunk_size)

                if len(data) == 0:
                    break
                    
                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    if "result" in result:
                        text, segment = parse_vosk_result(result["result"])
                        self.new_segment_transcribed.emit(text, segment)
            
            if not self.must_stop:
                result = json.loads(self.recognizer.FinalResult())
                if "result" in result:
                    text, segment = parse_vosk_result(result["result"])
                    self.new_segment_transcribed.emit(text, segment)
            
                # The 'finished' signal should be sent only if
                # the recognizer wasn't interrupted by the user
                self.finished.emit()
        
        except Exception as e:
            self.message.emit(f"Error during transcription: {e}")

        finally:
            if process:
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

                if process.poll() is not None:
                    try:
                        process.terminate()
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


    @Slot(list)
    def transcribeSegments(self, file_path: str, segments: list):
        self.must_stop = False
        for i, (seg_id, start, end) in enumerate(segments):
            self.message.emit(f"Transcribing {i+1}/{len(segments)}")
            text = self._transcribeSegment(file_path, start, end-start)
            if self.must_stop:
                break
            self.segment_transcribed.emit(text, start, end, seg_id, i)
        if not self.must_stop:
            # The 'finished' signal should be sent only when
            # the recognizer wasn't interrupted
            self.finished.emit()


    def _transcribeSegment(
            self,
            file_path: str,
            start_time: float, 
            duration: float,
        ) -> str:
        """ 
        Transcribe a segment of an audio file by streaming from ffmpeg to Vosk
        
        Args:
            input_file: Path to the audio file
            start_time: Start time in seconds
            duration: Duration of segment in seconds
            
        Returns:
            Transcribed text from the segment
        """
        
        self.recognizer.Reset()    # We won't be using the timecodes here anyway
        
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "error",     # Reduce ffmpeg output to bare minimum
            "-i", file_path,
            "-ss", str(start_time),
            "-t", str(duration),
            "-ar", str(self.SAMPLE_RATE), "-ac", "1", # 16kHz sample rate, single channel
            "-f", "s16le",                            # 16-bit signed little-endian PCM
            "-",                                      # Output to stdout
        ]
        
        process = None
        try:
            process = subprocess.Popen(
                ffmpeg_cmd, 
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # Process the audio stream in chunks
            chunk_size = 4000
            text_parts = []
            self.must_stop = False
            while not self.must_stop:
                data = process.stdout.read(chunk_size)
                if len(data) == 0:
                    break
                    
                if self.recognizer.AcceptWaveform(data):
                    text_parts.append(json.loads(self.recognizer.Result())["text"])
            
            if not self.must_stop:
                text_parts.append(json.loads(self.recognizer.FinalResult())["text"])
        
        except Exception as e:
            self.message.emit(f"Error during transcription: {e}")

        finally:
            if process:
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()

                if process.poll() is not None:
                    try:
                        process.terminate()
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
        
        return postProcessText(' '.join(text_parts))