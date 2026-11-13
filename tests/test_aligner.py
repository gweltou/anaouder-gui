import anaouder.lang as lang
from anaouder.services.aligner import smart_split_text


def test_aligner_word_boundary():
    lang.loadLanguage("br")

    vosk_tokens = [
        (64.738649, 64.978649, "d'am", 0.881606, "br"),
        (64.978649, 65.218649, "soñj", 1.0, "br"),
        (65.21932, 65.338649, "ar", 1.0, "br"),
        (65.338649, 65.608649, "pezh", 1.0, "br"),
        (65.608649, 65.668649, "a", 1.0, "br"),
        (65.668649, 66.328649, "zo", 1.0, "br"),
        (66.568649, 67.318649, "bepred", 0.996026, "br"),
        (68.01113, 68.458758, "skridoù", 0.991505, "br"),
        (68.458758, 68.784308, "met", 0.793422, "br"),
        (68.794344, 69.208649, "skridoù", 0.998138, "br"),
        (69.209096, 69.328705, "ar", 0.881043, "br"),
        (69.328705, 69.508649, "re", 0.995739, "br"),
        (69.508649, 69.658139, "all", 0.995246, "br"),
        (69.658139, 69.718649, "a", 0.995, "br"),
        (69.718649, 69.838649, "zo", 1.0, "br"),
        (69.838649, 70.168649, "bepred", 0.978932, "br"),
        (70.168649, 70.28864899999999, "ar", 1.0, "br"),
        (70.28864899999999, 70.618649, "fed", 0.740327, "br"),
        (70.948649, 71.453295, "bezañ", 0.90982, "br"),
        (71.453295, 71.938649, "euh", 0.947782, "br"),
        (72.268649, 72.598649, "feñ", 0.948656, "br"),
        (73.798649, 74.188649, "war", 1.0, "br"),
        (74.188649, 74.338202, "an", 0.981327, "br"),
        (74.338649, 74.767107, "hent", 0.769109, "br"),
        (74.78864899999999, 75.028649, "d'ar", 0.918546, "br"),
        (75.028649, 75.268649, "marv", 0.611716, "br"),
        (75.294421, 75.658649, "betek", 1.0, "br"),
        (75.658649, 75.748649, "ar", 1.0, "br"),
        (75.748649, 76.108649, "marv", 1.0, "br"),
        (76.108861, 76.378649, "kwa", 1.0, "br"),
    ]
    text = "D'am soñj ar pezh a zo bepred em skridoù, met skridoù ar re all, a zo bepred ar fed bezañ euh, feñ... war an hent d'ar- ma- betek ar marv kwa. "

    i = 0
    while (i := text.find(" ", i)) != -1:
        left, right = smart_split_text(text, i, vosk_tokens)
        i += 1
        print(left, right)
        assert not left or left[0] < left[1]
        assert not right or right[0] < right[1]


def test_aligner_in_word():
    lang.loadLanguage("br")

    vosk_tokens = [
        (64.738649, 64.978649, "d'am", 0.881606, "br"),
        (64.978649, 65.218649, "soñj", 1.0, "br"),
        (65.21932, 65.338649, "ar", 1.0, "br"),
        (65.338649, 65.608649, "pezh", 1.0, "br"),
        (65.608649, 65.668649, "a", 1.0, "br"),
        (65.668649, 66.328649, "zo", 1.0, "br"),
        (66.568649, 67.318649, "bepred", 0.996026, "br"),
        (68.01113, 68.458758, "skridoù", 0.991505, "br"),
        (68.458758, 68.784308, "met", 0.793422, "br"),
        (68.794344, 69.208649, "skridoù", 0.998138, "br"),
        (69.209096, 69.328705, "ar", 0.881043, "br"),
        (69.328705, 69.508649, "re", 0.995739, "br"),
        (69.508649, 69.658139, "all", 0.995246, "br"),
        (69.658139, 69.718649, "a", 0.995, "br"),
        (69.718649, 69.838649, "zo", 1.0, "br"),
        (69.838649, 70.168649, "bepred", 0.978932, "br"),
        (70.168649, 70.28864899999999, "ar", 1.0, "br"),
        (70.28864899999999, 70.618649, "fed", 0.740327, "br"),
        (70.948649, 71.453295, "bezañ", 0.90982, "br"),
        (71.453295, 71.938649, "euh", 0.947782, "br"),
        (72.268649, 72.598649, "feñ", 0.948656, "br"),
        (73.798649, 74.188649, "war", 1.0, "br"),
        (74.188649, 74.338202, "an", 0.981327, "br"),
        (74.338649, 74.767107, "hent", 0.769109, "br"),
        (74.78864899999999, 75.028649, "d'ar", 0.918546, "br"),
        (75.028649, 75.268649, "marv", 0.611716, "br"),
        (75.294421, 75.658649, "betek", 1.0, "br"),
        (75.658649, 75.748649, "ar", 1.0, "br"),
        (75.748649, 76.108649, "marv", 1.0, "br"),
        (76.108861, 76.378649, "kwa", 1.0, "br"),
    ]
    text = "D'am soñj ar pezh a zo bepred em skridoù, met skridoù ar re all, a zo bepred ar fed bezañ euh, feñ... war an hent d'ar- ma- betek ar marv kwa. "

    for i in range(len(text)):
        left, right = smart_split_text(text, i, vosk_tokens)
        print(left, right)
        assert not left or left[0] < left[1]
        assert not right or right[0] < right[1]


def test_segments_from_alignment_keeps_one_entry_per_sentence():
    """#50: a sentence with no words must still yield an entry (None)"""
    from anaouder.services.aligner import segments_from_alignment

    alignment = [
        ("||", None),
        ("demat", ("demat", 1.0, 1.5)),
        ("dit", ("dit", 1.5, 2.0)),
        ("||", None),
        # Second sentence normalizes to no words (e.g. "...")
        ("||", None),
        (None, ("euh", 2.0, 2.2)),  # Inserted token, ignored
        ("kenavo", None),
        ("deoc'h", ("deoc'h", 3.0, 3.4)),
        ("||", None),
        ("unaligned", None),
        ("||", None),
    ]
    assert segments_from_alignment(alignment) == [
        [1.0, 2.0],
        None,
        [3.0, 3.4],
        None,
    ]


def test_aligner_worker_with_empty_sentence():
    """#50: end-to-end alignment with a punctuation-only sentence"""
    from anaouder.services.aligner import (
        SENTENCE_SEPARATOR,
        align_text_with_vosk_tokens,
        segments_from_alignment,
    )

    lang.loadLanguage("br")
    tokens = [
        (0.0, 0.5, "demat", 1.0, "br"),
        (0.5, 1.0, "dit", 1.0, "br"),
        (2.0, 2.5, "kenavo", 1.0, "br"),
    ]
    sentences = ["Demat dit !", "...", "Kenavo."]
    sep = SENTENCE_SEPARATOR
    text = f"{sep} " + f" {sep} ".join(sentences) + f" {sep} "
    segments = segments_from_alignment(align_text_with_vosk_tokens(text, tokens))
    assert segments == [[0.0, 1.0], None, [2.0, 2.5]]


def test_text_aligner_disconnects_recognizer():
    """#49: connections made on the shared recognizer must not outlive autoAlign"""
    from PySide6.QtCore import QObject, Signal
    from PySide6.QtWidgets import QApplication
    from anaouder.services.aligner import TextAligner

    app = QApplication.instance() or QApplication([])

    class FakeRecognizer(QObject):
        progress = Signal(float)
        finished = Signal()

    class FakeDocument:
        undo_stack = None

    recognizer = FakeRecognizer()
    aligner = TextAligner(None, FakeDocument(), None, recognizer)
    calls = []

    def start_alignment():
        aligner._disconnect_recognizer()
        calls.append(1)

    aligner._connect_recognizer(recognizer.progress, aligner._on_hidden_transcription_progress)
    aligner._connect_recognizer(recognizer.finished, start_alignment)

    recognizer.finished.emit()
    recognizer.finished.emit()  # A later, unrelated transcription
    assert calls == [1]
    assert aligner._recognizer_connections == []

    # Cancel path: disconnect without `finished` being emitted
    aligner._connect_recognizer(recognizer.finished, start_alignment)
    aligner._disconnect_recognizer()
    recognizer.finished.emit()
    assert calls == [1]
