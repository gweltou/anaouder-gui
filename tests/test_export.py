import pytest

from PySide6.QtWidgets import QWidget

from src.export import (
    ExportDialog,
    export,
    clean_subtitle_text,
    format_txt,
    format_srt,
    format_eaf
)


# --- FIXTURES ---

@pytest.fixture
def sample_utterances():
    """Returns a standard list of utterances for testing."""
    return [
        ("Hello world", (0.0, 1.5)),
        ("Second sentence", (2.0, 3.5)),
        ("<b>Bold</b> text", (4.0, 5.0))
    ]


def test_clean_subtitle_text():
    # 1. Standard cleanup
    text = "Hello <br> world"
    assert clean_subtitle_text(text) == "Hello\nworld"

    # 2. Allowed tags (SRT)
    text = "<b>Bold</b> and <i>Italic</i>"
    assert clean_subtitle_text(text) == "<b>Bold</b> and <i>Italic</i>"

    # 3. Forbidden tags
    text = "<span style='color:red'>Red</span>"
    assert clean_subtitle_text(text) == "Red"

    # 4. Special chars
    text = "*Metadata*"
    assert clean_subtitle_text(text) == "Metadata"


def test_format_srt(sample_utterances):
    # Override the mock parser specifically for this test logic if needed
    # The global mock returns the input text as regions[0]['text']
    
    result = format_srt(sample_utterances)
    
    # Check basics of SRT format
    assert "1" in result  # Index
    assert "00:00:00,000 --> 00:00:01,500" in result # Timestamp 1
    assert "Hello world" in result
    
    assert "3" in result # Index 3
    assert "<b>Bold</b> text" in result # Should keep formatting tags


def test_format_txt(sample_utterances):
    result = format_txt(sample_utterances)
    
    lines = result.split('\n')
    assert len(lines) == 3
    assert lines[0] == "Hello world"
    assert lines[2] == "Bold text" # format_txt strips HTML tags in your logic


def test_format_eaf(sample_utterances):
    # NOTE: There is a logic bug in the provided source code for format_eaf.
    # In the loop: `segment.append(segment)` calls append on a tuple.
    # We will Patch the function locally or Expect a crash if checking the bug,
    # but assuming the bug is fixed, here is the test:
    
    # Let's patch the bug in the module dynamically or catch the error to prove logic flow
    try:
        result = format_eaf(sample_utterances, "test.wav")
    except AttributeError:
        pytest.fail("Source code bug detected: 'tuple' object has no attribute 'append'. " 
                    "In format_eaf, change 'segment.append' to 'segments.append'")
        
    assert "ANNOTATION_DOCUMENT" in result
    assert "TIME_SLOT_ID=\"ts1\"" in result
    assert "Hello world" in result
    # Check millisecond conversion (1.5s -> 1500)
    assert 'TIME_VALUE="1500"' in result 


def test_dialog_defaults(qtbot):
    """Test the dialog UI initialization."""
    dialog = ExportDialog(None, default_path="/tmp/test.srt", file_type="srt")
    qtbot.addWidget(dialog)
    
    assert dialog.windowTitle() == "Export to SRT"
    assert dialog.file_path_input.text() == "/tmp/test.srt"