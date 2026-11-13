from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from src.main import MainWindow
from src.strings import app_strings
from src.ui.icons import loadIcons


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for all tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    loadIcons()
    app_strings.initialize()

    yield app

    # Cleanup after all tests
    app.quit()


@pytest.fixture
def main_window(qapp):
    """Create a fresh MainWindow for each test"""
    window = MainWindow()
    yield window
    # Cleanup after each test
    window.undo_stack.clear()
    window.close()
    window.deleteLater()
    qapp.processEvents()  # Process pending events


def load_document(main_window):
    main_window.waveform.clear()
    main_window.text_widget.clear()
    main_window.undo_stack.clear()

    for text, segment in [
        ("Linenn gentañ", (0.45, 2.25)),
        ("Eil linenn.", (18, 20)),
        ("Trede linenn", (25, 30)),
        ("Pevare linenn", (32, 35)),
        ("Pempvet linenn", (40, 41)),
    ]:
        seg_id = main_window.document_controller.addSegment(list(segment))
        main_window.text_widget.appendSentence(text, seg_id)


def load_document_2(main_window):
    main_window.waveform.clear()
    main_window.text_widget.clear()
    main_window.undo_stack.clear()
    main_window.openFile(Path("tests/Meli_mila_Malou_1.ali"))


def test_density(main_window):
    load_document(main_window)

    d = main_window.document_controller.getUtteranceDensity(0)
    assert 7 < d < 8

    # Updating density
    main_window.text_widget.setSentenceText("hello", 0)
    main_window.document_controller.updateUtteranceDensity(0)
    d = main_window.document_controller.getUtteranceDensity(0)
    assert 2 < d < 3

    # Joining
    first_density = main_window.document_controller.getUtteranceDensity(1)
    main_window.document_controller.joinUtterances([1, 2])
    # The joined utterance keeps the same seg_id as the first of the two joined sentences
    second_density = main_window.document_controller.getUtteranceDensity(1)
    assert second_density < first_density


def test_subtitle_rules_keep_formatting(main_window):
    """Splitting a block with the subtitle rules must keep text formatting (#33)"""
    from src.services.adapt_subtitles import apply_subtitle_rules
    from src.utils import EM_DASH, LINE_BREAK

    load_document(main_window)
    text_widget = main_window.text_widget
    controller = main_window.document_controller
    ITALIC = text_widget.TextFormat.ITALIC
    BOLD = text_widget.TextFormat.BOLD

    block = text_widget.document().findBlockByNumber(1)
    original = [
        (f"{EM_DASH} Demat ", set()),
        ("Yann", {ITALIC}),
        (f". {EM_DASH} ", set()),
        ("Mat ar jeu", {ITALIC, BOLD}),
        (" ?", set()),
    ]
    text_widget.setBlockFragments(block, original)
    original_html = text_widget.getBlockHtmlAndMask(block)[0]

    apply_subtitle_rules(controller, block, block, main_window.undo_stack, 0.0)

    block = text_widget.document().findBlockByNumber(1)
    assert block.text() == f"{EM_DASH} Demat Yann.{LINE_BREAK}{EM_DASH} Mat ar jeu ?"
    fragments = [(t, f) for t, f in text_widget.getBlockFragments(block) if t]
    assert ("Yann", {ITALIC}) in fragments
    assert ("Mat ar jeu", {ITALIC, BOLD}) in fragments
    # Other blocks are untouched
    assert text_widget.document().findBlockByNumber(0).text() == "Linenn gentañ"

    main_window.undo_stack.undo()
    block = text_widget.document().findBlockByNumber(1)
    assert text_widget.getBlockHtmlAndMask(block)[0] == original_html
