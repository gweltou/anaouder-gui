"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025-2026 Gweltaz Duval-Guennoc (gwel@ik.me)

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

from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol

from PySide6.QtGui import (
    QSyntaxHighlighter,
    QTextBlock,
    QTextBlockUserData,
    QTextCursor,
    QTextDocument,
    QUndoStack,
)

# Custom types

type Segment = list[float]
type SegmentId = int


class BlockType(Enum):
    EMPTY_OR_COMMENT = 0
    METADATA_ONLY = 1
    ALIGNED = 2
    NOT_ALIGNED = 3


class MyTextBlockUserData(QTextBlockUserData):
    """
    Fields:
        - seg_id
    """

    def __init__(self, data: dict):
        super().__init__()
        self.data = data

    def clone(self):
        # This method is required by QTextBlockUserData.
        # It should return a copy of the user data object.
        return MyTextBlockUserData(self.data)


class MainWindowInterface(Protocol):
    def setStatusMessage(self, message: str, timeout: int) -> None: ...

    def setErrorMessage(self, message: str, timeout: int) -> None: ...

    def getOpenFileDialog(self, title: str, filter: str) -> str | None: ...


class DocumentInterface(Protocol):
    media_path: Path | None
    undo_stack: QUndoStack
    segments: dict[SegmentId, Segment]
    must_sort: bool

    def getSegment(self, segment_id: SegmentId) -> Segment | None: ...

    def addSegment(
        self, segment: Segment, segment_id: SegmentId | None = None
    ) -> SegmentId: ...

    def updateSegment(self, segment_id: SegmentId, segment: Segment) -> None: ...

    def removeSegment(self, segment_id: SegmentId) -> None: ...

    def deleteUtterances(self, segment_ids: list[SegmentId]) -> None: ...

    def getSortedSegments(self) -> list[tuple[SegmentId, Segment]]: ...

    def getNewSegmentId(self) -> SegmentId: ...

    def getPrevSegmentId(self, segment_id: SegmentId) -> SegmentId: ...

    def getNextSegmentId(self, segment_id: SegmentId) -> SegmentId: ...

    def getNextAlignedBlock(self, block: QTextBlock) -> QTextBlock | None: ...

    def getPrevAlignedBlock(self, block: QTextBlock) -> QTextBlock | None: ...

    def getBlockType(self, block: QTextBlock) -> BlockType: ...

    def getBlockByNumber(self, block_number: int) -> QTextBlock | None: ...

    def getBlockById(self, segment_id: SegmentId) -> QTextBlock | None: ...

    def getBlockId(self, block: QTextBlock) -> SegmentId: ...

    def setBlockId(self, block: QTextBlock, segment_id: SegmentId | None) -> None: ...

    def getBlockHtml(self, block: QTextBlock) -> str | None: ...

    def getTranscriptionForSegment(
        self, segment_start: float, segment_end: float
    ) -> list: ...

    def updateBlockMetadata(self, block: QTextBlock, metadata: dict) -> None: ...

    def setBlockMetadata(self, block: QTextBlock, metadata: dict | None) -> None: ...

    def getBlockMetadata(self, block: QTextBlock) -> dict: ...

    def getSentenceLength(self, block: QTextBlock) -> int: ...

    def getUtteranceDensity(self, segment_id: SegmentId) -> float: ...

    def updateUtteranceDensity(self, segment_id: SegmentId) -> None: ...

    def getSelectedBlocksAndTimeRange(self) -> tuple[list[QTextBlock], list] | None: ...

    def splitUtteranceAtPlayhead(self) -> None: ...

    def splitUtteranceAtCharPos(self, segment_id: SegmentId, position: int) -> None: ...

    def moveHead(self) -> None: ...

    def moveTail(self) -> None: ...

    def clear(self) -> None: ...

    def getData(self) -> list[tuple[str, Segment | None]]: ...

    def loadData(self, data: list[tuple[str, Segment | None]]) -> None: ...


class WaveformInterface(Protocol):
    """Anything with these methods can be used"""

    active_segments: list[SegmentId]
    active_segment_id: SegmentId
    must_redraw: bool
    _selection: Segment | None

    @property
    def refresh_segment_info(self) -> Any: ...

    def getSelection(self) -> Segment | None: ...

    def removeSelection(self) -> None: ...

    def setRecognizerProgress(self, time_s: float) -> None: ...


class TextEditorInterface(Protocol):
    highlighter: QSyntaxHighlighter
    highlighted_sentence_id: SegmentId

    def document(self) -> QTextDocument: ...

    def textCursor(self) -> QTextCursor: ...

    def setTextCursor(self, cursor: QTextCursor, /) -> None: ...

    def appendSentence(
        self, text: str, segment_id: SegmentId | None
    ) -> QTextBlock: ...

    def insertBlock(self, text: str, data: dict | None, pos: int) -> QTextBlock: ...

    def insertSentenceWithId(
        self, text: str, segment_id: SegmentId, with_cursor: bool = False
    ) -> None: ...

    def setSentenceText(self, text: str, segment_id: SegmentId) -> None: ...

    def deleteSentence(self, seg_id: SegmentId) -> None: ...

    def deactivateSentence(self, seg_id: SegmentId | None) -> None: ...

    def getBlockNumber(self, position: int) -> int: ...

    def getBlockHtmlMap(self, block: QTextBlock) -> tuple[str, list[bool]]: ...

    def isAligned(self, block: QTextBlock) -> bool: ...

    def updateLineNumberAreaWidth(self) -> None: ...

    def updateLineNumberArea(self) -> None: ...

    def updatePlayerPosition(self, float) -> None: ...

    def getCursorState(self) -> dict: ...

    def setCursorState(self, cursor_state: dict) -> None: ...

    def blockSignals(self, b: bool, /) -> bool: ...

    def signalsBlocked(self) -> bool: ...

    def highlightUtterance(self, segment_id: SegmentId) -> None: ...

    def getLineNumberAreaWidth(self) -> int: ...

    def printDocumentStructure(self) -> None: ...
