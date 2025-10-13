from typing import (
    Protocol,
    Dict, List, Tuple, Any,
    Optional
)
from PySide6.QtCore import (
    Signal,
)
from PySide6.QtGui import (
    QTextBlock, QTextDocument, QTextCursor,
    QSyntaxHighlighter
)


# Custom types

type Segment = List[float]
type SegmentId = int



class WaveformInterface(Protocol):
    """Anything with these methods can be used"""
    segments: Dict[SegmentId, Segment]
    active_segments: List[SegmentId]
    active_segment_id: SegmentId
    must_sort: bool
    must_redraw: bool
    _selection: Optional[Segment]

    @property
    def refresh_segment_info(self) -> Any:
        ...
    
    def addSegment(self, segment: Segment, seg_id: Optional[SegmentId] = None) -> SegmentId:
        """Add a segment and return its ID"""
        ...
    
    def getNewId(self) -> SegmentId:
        """Get a new unique segment ID"""
        ...
    
    def getSelection(self) -> Optional[Segment]:
        ...
    
    def deselect(self) -> None:
        ...



class TextDocumentInterface(Protocol):
    highlighter: QSyntaxHighlighter

    def document(self) -> QTextDocument:
        ...
    
    def textCursor(self) -> QTextCursor:
        ...

    def setTextCursor(self, cursor: QTextCursor, /) -> None:
        ... 
    
    def insertBlock(self, text: str, data: Optional[dict], pos: int) -> QTextBlock:
        ...

    def insertSentenceWithId(self, text: str, seg_id: SegmentId, with_cursor: bool) -> None:
        ...
    
    def setSentenceText(self, seg_id: SegmentId, text: str) -> None:
        ...

    def deleteSentence(self, seg_id: SegmentId) -> None:
        ...
    
    def deactivateSentence(self, seg_id: SegmentId) -> None:
        ...
    
    def setBlockId(self, block: QTextBlock, seg_id: SegmentId) -> None:
        ...

    def getBlockById(self, seg_id: SegmentId) -> Optional[QTextBlock]:
        ...
    
    def getBlockNumber(self, position: int) -> int:
        ...
    
    def getBlockHtml(self, block: QTextBlock) -> Tuple[str, List[bool]]:
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