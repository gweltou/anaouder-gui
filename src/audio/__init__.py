import subprocess
from collections.abc import Callable

import numpy as np


def stream_audio_file(
    input_file: str,
    sample_rate: int,
    callback: Callable,
    buffer_size = 8000,
):
    # Configure ffmpeg to output raw audio in the format we need
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', input_file,
        '-ar', str(sample_rate),  # 16kHz sample rate
        '-ac', '1',      # Mono
        '-f', 's16le',   # 16-bit signed little-endian PCM
        '-',             # Output to stdout
        '-loglevel', 'error'  # Reduce ffmpeg output
    ]

    with subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE
    ) as process:
        while True:
            data = process.stdout.read(buffer_size)
            if len(data) == 0:
                break
            callback(data)


def get_samples(path: str, sample_rate=16000, buffer_size=8000) -> np.ndarray:
    """Returns a Numpy array of normalized float32 samples from an audio file."""
    chunks = []

    def handle_buffer(data):
        chunks.append(data)

    try:
        stream_audio_file(path, sample_rate, handle_buffer, buffer_size)
    except Exception as e:
        raise RuntimeError(f"Failed to stream audio file '{path}': {e}") from e

    if chunks:
        raw_data = b''.join(chunks)
        samples = np.frombuffer(raw_data, dtype=np.int16)
        normalized_samples = samples.astype(np.float32) / 32768.0
        return normalized_samples
    else:
        return np.array([], dtype=np.float32)
