from pathlib import Path
from src.cache_system import cache


test_dir = Path(__file__).parent


def test_cache_system():
    media_path = test_dir / "MeliMilaMalou.wav"
    media_metadata = cache.get_media_metadata(media_path)
    print(media_metadata)

    assert "file_size" in media_metadata
    assert type(media_metadata["file_size"]) == int
    assert "file_path" in media_metadata
    assert type(media_metadata["file_path"]) == str
    assert "waveform_size" in media_metadata
    assert type(media_metadata["waveform_size"]) == int
    assert "last_access" in media_metadata
    assert "fingerprint" in media_metadata

    doc_path = test_dir / "MeliMilaMalou.ali"
    doc_metadata = cache.get_doc_metadata(doc_path)
    print(doc_metadata)

    assert "file_path" in doc_metadata
    assert "cursor_pos" in doc_metadata
    assert "waveform_pos" in doc_metadata
    assert "waveform_pps" in doc_metadata
    assert "show_scenes" in doc_metadata
    assert "show_margin" in doc_metadata
    assert "video_open" in doc_metadata
    assert "last_access" in doc_metadata


def test_cache_transcription():
    media_path = test_dir / "MeliMilaMalou.wav"
    backup_transcription = cache.get_media_transcription(media_path)
    if backup_transcription is None:
        backup_transcription = []
    else:
        backup_transcription = backup_transcription.copy()
    
    cache.set_media_transcription(media_path, [])

    transcription = cache.get_media_transcription(media_path)

    assert transcription == []

    print(backup_transcription)


def test_cache_waveform():
    media_path = test_dir / "MeliMilaMalou.wav"
    waveform = cache.get_waveform(media_path)