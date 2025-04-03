import locale
import platform
from pathlib import Path

from PySide6.QtCore import (
    QThread, Signal,
)

from ostilhou.asr.models import load_model, is_model_loaded
from ostilhou.asr import (
    transcribe_segment_timecoded_callback,
    transcribe_segment_ffmpeg,
    transcribe_file_timecoded_callback_ffmpeg,
)

from src.utils import _get_cache_directory
from src.lang import postProcessText


_loaded_model = None
_loaded_model_path = None



class RecognizerWorker(QThread):
    message = Signal(str)
    transcribedSegment = Signal(str, float, float, int, int) # Transcribe a pre-defined segment
    transcribed = Signal(str, list) # Create a segment with transcription
    
    def setModelPath(self, model_path):
        print("Recognizer model path set to", model_path)
        self.model_path = model_path
    
    def setArgs(self, audio_path: str, segments: list):
        self.audio_path = audio_path
        self.segments = segments
    
    def run(self):
        global _loaded_model, _loaded_model_path

        if self.model_path != _loaded_model_path:
            self.message.emit(f"Loading {self.model_path}")
            model_path : Path = _get_cache_directory("models") / self.model_path
            _loaded_model = load_model(model_path.as_posix())
            _loaded_model_path = self.model_path
        
        # Stupid hack with locale to avoid commas in json string
        current_locale = locale.getlocale()
        print(f"{current_locale=}")
        if platform.system() == "Linux":
            locale.setlocale(locale.LC_ALL, ("C", "UTF-8"))
        else:
            locale.setlocale(locale.LC_ALL, ("en_us", "UTF-8")) # locale en_US works on macOS
        print(f"{locale.getlocale()=}")
        
        if self.segments:
            # segments already exist in 
            for i, (seg_id, start, end) in enumerate(self.segments):
                self.message.emit(f"{i+1}/{len(self.segments)}")
                # text = transcribe_segment(self.audio_data[start*1000:end*1000])
                text = transcribe_segment_ffmpeg(self.audio_path, start, end-start, model=_loaded_model)
                text = ' '.join(text)
                text = postProcessText(text)
                print(f"STT: {text}")
                self.transcribedSegment.emit(text, start, end, seg_id, i)
        else:
            # Transcribe whole file
            def parse_vosk_result(result):
                text = []
                for vosk_token in result:
                    text.append(vosk_token['word'])
                text = postProcessText(' '.join(text))
                segment = [result[0]['start'], result[-1]['end']]
                self.transcribed.emit(text, segment)
            
            self.message.emit(f"Transcribing...")
            transcribe_file_timecoded_callback_ffmpeg(self.audio_path, parse_vosk_result)
        locale.setlocale(locale.LC_ALL, current_locale)