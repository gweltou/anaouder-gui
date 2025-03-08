import locale
import platform

from PySide6.QtCore import (
    QThread, Signal,
)

from ostilhou.asr.models import load_model, is_model_loaded
from ostilhou.asr import (
    transcribe_segment_timecoded_callback,
    transcribe_segment_ffmpeg,
    transcribe_file_timecoded_callback_ffmpeg,
)



class RecognizerWorker(QThread):
    message = Signal(str)
    transcribedSegment = Signal(str, int, int) # Transcribe a pre-defined segment
    transcribed = Signal(str, list) # Create a segment with transcription
    
    def setModel(self, model_name):
        self.model = model_name
    
    def setArgs(self, audio_path: str, segments: list):
        self.audio_path = audio_path
        self.segments = segments
    
    def run(self):
        if not is_model_loaded(self.model):
            self.message.emit(f"Loading {self.model}")
            load_model(self.model)
        
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
                text = transcribe_segment_ffmpeg(self.audio_path, start, end-start, model=None)
                text = ' '.join(text)
                print(f"STT: {text}")
                self.transcribedSegment.emit(text, seg_id, i)
        else:
            # Transcribe whole file
            def parse_vosk_result(result):
                text = []
                for vosk_token in result:
                    text.append(vosk_token['word'])
                segment = [result[0]['start'], result[-1]['end']]
                self.transcribed.emit(' '.join(text), segment)
            
            self.message.emit(f"Transcribing...")
            transcribe_file_timecoded_callback_ffmpeg(self.audio_path, parse_vosk_result)
        locale.setlocale(locale.LC_ALL, current_locale)