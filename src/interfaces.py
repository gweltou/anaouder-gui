from typing import (
    Protocol,
    Dict, List, Tuple, Any,
    Optional
)
from enum import Enum

from PySide6.QtCore import (
    Signal,
)
from PySide6.QtGui import (
    QUndoStack,
    QTextBlock, QTextDocument, QTextCursor,
    QSyntaxHighlighter
)


# Custom types

type Segment = List[float]
type SegmentId = int


class BlockType(Enum):
    EMPTY_OR_COMMENT = 0
    METADATA_ONLY = 1
    ALIGNED = 2
    NOT_ALIGNED = 3



class DocumentInterface(Protocol):
    undo_stack: QUndoStack
    segments: Dict[SegmentId, Segment]
    must_sort: bool

    def getSegment(self, segment_id: SegmentId) -> Optional[Segment]:
        ...

    def addSegment(self, segment: Segment, segment_id: Optional[SegmentId] = None) -> SegmentId:
        """Add a segment and return its ID"""
        ...
    
    def removeSegment(self, segment_id: SegmentId) -> None:
        ...
    
    def getSortedSegments(self) -> List[Tuple[SegmentId, Segment]]:
        ...
    
    def getNewSegmentId(self) -> SegmentId:
        """Get a new unique segment ID"""
        ...
    
    def getBlockType(self, block: QTextBlock) -> BlockType:
        ...
    
    def getBlockById(self, segment_id: SegmentId) -> Optional[QTextBlock]:
        ...
    
    def setBlockId(self, block: QTextBlock, segment_id: Optional[SegmentId]) -> None:
        ...


class WaveformInterface(Protocol):
    """Anything with these methods can be used"""
    active_segments: List[SegmentId]
    active_segment_id: SegmentId
    must_redraw: bool
    _selection: Optional[Segment]

    @property
    def refresh_segment_info(self) -> Any:
        ...
    
    def getSelection(self) -> Optional[Segment]:
        ...
    
    def removeSelection(self) -> None:
        ...



class TextDocumentInterface(Protocol):
    highlighter: QSyntaxHighlighter

    def document(self) -> QTextDocument:
        ...
    
    def textCursor(self) -> QTextCursor:
        ...

    def setTextCursor(self, cursor: QTextCursor, /) -> None:
        ... 
    
    def appendSentence(self, text: str, segment_id: Optional[SegmentId]) -> QTextBlock:
        ...
    
    def insertBlock(self, text: str, data: Optional[dict], pos: int) -> QTextBlock:
        ...

    def insertSentenceWithId(self, text: str, segment_id: SegmentId, with_cursor: bool = False) -> None:
        ...
    
    def setSentenceText(self, text: str, segment_id: SegmentId) -> None:
        ...

    def deleteSentence(self, seg_id: SegmentId) -> None:
        ...
    
    def deactivateSentence(self, seg_id: SegmentId) -> None:
        ...
    
    def getBlockById(self, seg_id: SegmentId) -> Optional[QTextBlock]:
        ...
    
    def getBlockNumber(self, position: int) -> int:
        ...
    
    def getBlockHtml(self, block: QTextBlock) -> Tuple[str, List[bool]]:
        ...
    
    def updateLineNumberAreaWidth(self) -> None:
        ...

    def updateLineNumberArea(self) -> None:
        ...

    def getCursorState(self) -> dict:
        ...
    
    def setCursorState(self, cursor_state: dict) -> None:
        ...
    
    def blockSignals(self, b: bool, /) -> bool:
        ...
    
    def signalsBlocked(self) -> bool:
        ...
    
    def highlightUtterance(self, seg_id: SegmentId) -> None:
        ...