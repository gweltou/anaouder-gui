from typing import List, Tuple, Dict, Optional
import logging

from ostilhou.asr import extract_metadata

from PySide6.QtGui import (
    QTextBlock, QUndoStack,
    QTextCursor
)
from PySide6.QtCore import QObject, Signal
from src.interfaces import (
    BlockType,
    Segment, SegmentId,
)
from src.text_widget import TextEditWidget
from src.waveform_widget import WaveformWidget
from src.utils import (
    MyTextBlockUserData,
    LINE_BREAK
)
from src.commands import (
    AddSegmentCommand, ResizeSegmentCommand,
    DeleteUtterancesCommand, JoinUtterancesCommand,
    InsertBlockCommand,
    MoveTextCursor
)
from src.aligner import (
    align_text_with_vosk_tokens,
    smart_split_text, smart_split_time,
    SmartSplitError
)
from src.strings import strings



log = logging.getLogger(__name__)



class DocumentController(QObject):
    message = Signal(str)


    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

        self.media_metadata = {}
        self.segments = {}
        self._sorted_segments = []

        self.text_widget: Optional[TextEditWidget] = None
        self.waveform_widget: Optional[WaveformWidget] = None

        self.must_sort = False
        self.id_counter = 0
        self.undo_stack = QUndoStack()

        self.memoized_segment = None # Memoized transcription for one segment
        self.memoized_transcription_tokens = []
    

    def clear(self) -> None:
        """ Clears the document """
        self.clearSegments()
        
        if self.text_widget is not None:
            self.text_widget.document().clear()
            self.text_widget.updateLineNumberAreaWidth()
            self.text_widget.updateLineNumberArea()
        
        self.undo_stack.clear()


    def setTextWidget(self, text_widget: TextEditWidget) -> None:
        self.text_widget = text_widget
    
    def setWaveformWidget(self, waveform_widget: WaveformWidget) -> None:
        self.waveform_widget = waveform_widget
    

    def loadDocumentData(self, data: List[Tuple[str, Optional[Segment]]]) -> None:
        """
        Load a document into the text widget and waveform.
        
        Args:
            data (list): List of document blocks (text, Segment)
        """
        # TODO: This function seems quite slow

        if self.text_widget is None:
            return

        self.clear()

        was_blocked = self.text_widget.document().blockSignals(True)
        for text, segment in data:
            segment_id = self.addSegment(segment) if segment else None
            self.text_widget.appendSentence(text, segment_id)
        self.text_widget.document().blockSignals(was_blocked)
        
        self.text_widget.updateLineNumberAreaWidth()
        self.text_widget.updateLineNumberArea()


    def setMediaMetadata(self, metadata: dict) -> None:
        self.media_metadata = metadata
    

    def getMediaMetadata(self) -> dict:
        print(f"{self.media_metadata=}")
        return self.media_metadata
    
    
    def getBlockByNumber(self, block_number: int) -> Optional[QTextBlock]:
        if self.text_widget is None:
            return None
        
        block = self.text_widget.document().findBlockByNumber(block_number)
        print(f"{block=}")
        return block


    def getBlockNumber(self, position: int) -> int:
        block = self.findBlock(position)
        if block is None:
            return -1
        return block.blockNumber()


    def findBlock(self, position: int) -> Optional[QTextBlock]:
        if self.text_widget is None:
            return None
        
        document = self.text_widget.document()
        pos = document.findBlock(position)
        return pos if pos != -1 else None


    def setBlockId(self, block: QTextBlock, segment_id: Optional[SegmentId]) -> None:
        """
        Set the segment id of a given block
        
        Args:
            block (QTextBlock)
            segment_id: SegmentId or None
        """
        log.debug(f"setBlockId({block=}, {segment_id=})")
        if segment_id is None:
            block.setUserData(None)
        elif not block.userData():
            block.setUserData(MyTextBlockUserData({"seg_id": segment_id}))
        else:
            user_data = block.userData().data
            user_data["seg_id"] = segment_id
        
        self.text_widget.highlighter.rehighlightBlock(block)


    def getBlockId(self, block: QTextBlock) -> int:
        """Return utterance id associated to block or -1"""
        if not block.userData():
            return -1
        
        user_data = block.userData().data
        if "seg_id" in user_data:
            return user_data["seg_id"]
        
        return -1
    

    def getBlockById(self, segment_id: SegmentId) -> Optional[QTextBlock]:
        if self.text_widget is None:
            return None
        
        document = self.text_widget.document()
        block = document.firstBlock()
        while block.isValid():
            if block.userData():
                if block.userData().data["seg_id"] == segment_id:
                    return block
            block = block.next()
        return None
    

    def getBlockType(self, block: QTextBlock) -> BlockType:
        text = block.text()

        # Find and crop comments
        i = text.find('#')
        if i >= 0:
            text = text[:i]
        text = text.strip()

        if not text:
            return BlockType.EMPTY_OR_COMMENT
        
        text, metadata = extract_metadata(text) # deprecated
        if metadata and not text.strip():
            return BlockType.METADATA_ONLY

        # This block is a sentence, check if it is aligned or not
        if not block.userData():
            return BlockType.NOT_ALIGNED
        
        user_data = block.userData().data
        if "seg_id" in user_data:
            segment_id = user_data["seg_id"]
            if segment_id in self.segments:
                return BlockType.ALIGNED
        
        return BlockType.NOT_ALIGNED


    def getNewSegmentId(self) -> SegmentId:
        """Returns the next available segment ID"""
        seg_id = self.id_counter
        self.id_counter += 1
        return seg_id
    

    def addSegment(self, segment: Segment, segment_id: Optional[SegmentId] = None) -> SegmentId:
        log.debug(f"addSegment({segment=}, {segment_id=})")
        if segment_id == None:
            segment_id = self.getNewSegmentId()
        self.segments[segment_id] = segment

        self.must_sort = True
        self.waveform_widget.must_redraw = True
        return segment_id
        

    def getSegment(self, segment_id: SegmentId) -> Optional[Segment]:
        if segment_id in self.segments:
            return self.segments[segment_id]
        return None


    def removeSegment(self, segment_id: SegmentId) -> None:
        if segment_id in self.segments:
            del self.segments[segment_id]
            self.must_sort = True
            self.waveform_widget.must_redraw = True
    

    def clearSegments(self) -> None:
        # Keys are segment ids (int), values are segment [start (float), end (float)]
        self.segments: Dict[SegmentId, Segment] = dict()
        self.waveform_widget.active_segments = []
        self.waveform_widget.active_segment_id = -1
        self.waveform_widget.must_redraw = True

    
    def getSortedSegments(self) -> List[Tuple[SegmentId, Segment]]:
        """Return the list of (SegmentId, Segment), sorted by start time"""
        if self.must_sort:
            self._sorted_segments = sorted(self.segments.items(), key=lambda x: x[1])
            self.must_sort = False
        return self._sorted_segments


    def getNextAlignedBlock(self, block: QTextBlock) -> Optional[QTextBlock]:
        while True:
            block = block.next()

            if not block.isValid():
                return None
            
            if self.getBlockType(block) == BlockType.ALIGNED:
                return block


    def getPrevAlignedBlock(self, block: QTextBlock) -> Optional[QTextBlock]:
        while True:
            block = block.previous()

            if not block.isValid():
                return None
            
            if self.getBlockType(block) == BlockType.ALIGNED:
                return block


    def getSegmentAtTime(self, position_sec: float) -> SegmentId:
        """Return the ID of any segment at a given position, or -1 if none is present"""
        log.debug(f"getSegmentAtTime({position_sec=})")
        for segment_id, (start, end) in self.getSortedSegments():
            # Give precedence to the segment that starts at this timecode
            # rather than the one that ends at this timecode
            if start - 0.001 <= position_sec < end:
                return segment_id
        return -1
    

    def cropHead(self):
        log.debug("cropHead")
        if self.waveform_widget is None:
            return
        
        if self.waveform_widget.active_segment_id >= 0:
            active_segment_id = self.waveform_widget.active_segment_id
            playhead = self.waveform_widget.playhead
            segment = self.segments[active_segment_id]

            if segment[0] <= playhead <= segment[1]:
                self.undo_stack.push(
                    ResizeSegmentCommand(
                        self,
                        self.waveform_widget,
                        active_segment_id,
                        playhead,
                        segment[1]
                    )
                )


    def cropTail(self):
        log.debug("cropTail")
        if self.waveform_widget is None:
            return
        
        active_segment_id = self.waveform_widget.active_segment_id
        playhead = self.waveform_widget.playhead
        
        if active_segment_id >= 0:
            segment = self.getSegment(active_segment_id)

            if segment and (segment[0] <= playhead <= segment[1]):
                self.undo_stack.push(
                    ResizeSegmentCommand(
                        self,
                        self.waveform_widget,
                        active_segment_id,
                        segment[0],
                        playhead
                    )
                )

    def getSubtitleAtPosition(self, position_sec: float) -> Tuple[SegmentId, str]:
        """
        Return (seg_id, sentence, tokens) or None
        if there is any utterance at that time position

        Args:
            position_sec (float): Time position
        
        Return:
            A tuple of:
                * SegmentID
                * HTML formatted sentence
                * List of transcription tokens
        """
        if self.text_widget is None:
            return (-1, "")

        seg_id = self.getSegmentAtTime(position_sec)
        if seg_id == -1:
            return (-1, "")
        
        # Remove metadata from subtitle text
        block = self.getBlockById(seg_id)
        if block is None:
            return (-1, "")

        html, _ = self.text_widget.getBlockHtml(block)
        return (seg_id, html)


    def getTranscriptionFor(self, segment_id: SegmentId) -> list:
        """ Return a list of transcription tokens """
        
        segment = self.getSegment(segment_id)
        if segment is None:
            return []
        
        if segment_id == self.memoized_segment:
            return self.memoized_transcription_tokens
        
        tokens = self.getTranscriptionForSegment(segment[0], segment[1])
        self.memoized_segment = segment_id
        self.memoized_transcription_tokens = tokens
        return tokens
    

    def getTranscriptionForSegment(self, segment_start: float, segment_end: float) -> list:
        """ Return a list of transcription tokens """
        
        assert segment_start < segment_end

        cached_transcription = self.media_metadata.get("transcription", [])
        if cached_transcription:
            # if segment_end <= cached_transcription[-1][1]:
            tr_len = len(cached_transcription)
            # Get tokens range corresponding to current segment
            i = 0
            while i < tr_len and cached_transcription[i][1] < segment_start:
                i += 1
            j = i
            while j < tr_len and cached_transcription[j][0] < segment_end:
                j += 1
            tokens_range = cached_transcription[i:j]
            return tokens_range
        return []


    def getUtterancesForExport(self) -> List[Tuple[str, Segment]]:
        """Return all sentences and segments for export"""
        if self.text_widget is None:
            return []
        
        utterances = []
        block = self.text_widget.document().firstBlock()
        while block.isValid():
            if self.getBlockType(block) == BlockType.ALIGNED:
                text = self.text_widget.getBlockHtml(block)[0]

                # Remove extra spaces
                lines = [' '.join(l.split()) for l in text.split(LINE_BREAK)]
                text = LINE_BREAK.join(lines)
            
                block_id = self.getBlockId(block)
                segment = self.getSegment(block_id)
                if segment:
                    utterances.append( (text, segment) )
            
            block = block.next()
        
        return utterances
    

    def splitFromText(self, segment_id: SegmentId, position: int) -> None:
        """
        Split audio segment, given a char relative position in sentence
        Called from the textEdit widget
        """
        log.debug(f"splitFromText({segment_id=}, {position=})")

        block = self.getBlockById(segment_id)
        segment = self.getSegment(segment_id)
        
        if block is None or segment is None:
            return
        
        seg_start, seg_end = segment
        text = block.text()

        left_text = text[:position].rstrip()
        right_text = text[position:].lstrip()
        left_seg = None
        right_seg = None

        # Check if we can "smart split"
        cached_transcription = self.getMediaMetadata().get("transcription", [])
        if cached_transcription:
            if seg_end <= cached_transcription[-1][1]:
                tr_len = len(cached_transcription)
                # Get tokens range corresponding to current segment
                i = 0
                while i < tr_len and cached_transcription[i][1] < seg_start:
                    i += 1
                j = i
                while j < tr_len and cached_transcription[j][0] < seg_end:
                    j += 1
                tokens_range = cached_transcription[i:j]

                try:
                    log.info('"Smart" splitting')
                    left_seg, right_seg = smart_split_text(text, position, tokens_range)
                    left_seg[0] = seg_start
                    right_seg[1] = seg_end
                except SmartSplitError as e:
                    log.warning(e)
                    self.message.emit(strings.TR_CANT_SMART_SPLIT + f": {e}")
                except Exception as e:
                    log.warning(e)
                    self.message.emit(strings.TR_CANT_SMART_SPLIT + f": {e}")

        if not left_seg or not right_seg:
            # Revert to naive splitting method
            dur = seg_end - seg_start
            pc = position / len(text)
            left_seg = [seg_start, seg_start + dur*pc - 0.05]
            right_seg = [seg_start + dur*pc + 0.05, seg_end]
            log.info("Ratio splitting")
        
        self.splitUtterance(segment_id, left_text, right_text, left_seg, right_seg)


    def splitFromWaveform(self, segment_id: SegmentId, timepos: float) -> None:
        block = self.getBlockById(segment_id)
        if block is None:
            return
        
        segment = self.getSegment(segment_id)
        if not segment:
            return
        
        seg_start, seg_end = segment
        text = block.text()

        left_seg = [seg_start, timepos]
        right_seg = [timepos, seg_end]
        left_text = None
        right_text = None

        # Check if we can "smart split"
        cached_transcription = self.getMediaMetadata().get("transcription", [])
        if cached_transcription:
            if seg_end <= cached_transcription[-1][1]:
                tr_len = len(cached_transcription)
                # Get tokens range corresponding to current segment
                i = 0
                while i < tr_len and cached_transcription[i][1] < seg_start:
                    i += 1
                j = i
                while j < tr_len and cached_transcription[j][0] < seg_end:
                    j += 1
                tokens_range = cached_transcription[i:j]

                try:
                    log.info("smart splitting")
                    left_text, right_text = smart_split_time(text, timepos, tokens_range)
                except Exception as e:
                    self.message.emit(strings.TR_CANT_SMART_SPLIT)
                    log.error(f"Could not smart split: {e}")

        if left_text is None or right_text is None:
            # Add en empty sentence after
            left_text = text[:]
            right_text = ""

        self.splitUtterance(segment_id, left_text, right_text, left_seg, right_seg)
    

    def splitUtterance(
            self,
            seg_id: SegmentId,
            left_text: str, right_text: str,
            left_seg: list, right_seg: list
        ) -> None:

        if self.text_widget is None or self.waveform_widget is None:
            return

        left_id = self.getNewSegmentId()
        right_id = self.getNewSegmentId()
        
        self.undo_stack.beginMacro("split utterance")
        self.undo_stack.push(DeleteUtterancesCommand(self, self.text_widget, self.waveform_widget, [seg_id]))
        self.undo_stack.push(AddSegmentCommand(self, self.waveform_widget, left_seg, left_id))
        print(f"{self.text_widget.textCursor().position()=}")
        self.undo_stack.push(
            InsertBlockCommand(
                self.text_widget,
                self.text_widget.textCursor().position(),
                seg_id=left_id,
                text=left_text,
                after=True
            )
        )
        self.undo_stack.push(AddSegmentCommand(self, self.waveform_widget, right_seg, right_id))
        self.undo_stack.push(
            InsertBlockCommand(
                self.text_widget,
                self.text_widget.textCursor().position(),
                seg_id=right_id,
                text=right_text,
                after=True
            )
        )
        # Set cursor at the beggining of the right utterance
        cursor = self.text_widget.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        self.undo_stack.push(
            MoveTextCursor(self.text_widget, cursor.position())
        )
        self.undo_stack.endMacro()

        # self.text_edit.setTextCursor(cursor)
        self.text_widget.highlightUtterance(right_id)
        self.waveform_widget.must_redraw = True


    def joinUtterances(self, segments_id) -> None:
        """
        Join many segments in one.
        Keep the segment ID of the earliest segment among the selected ones.
        """
        self.undo_stack.push(JoinUtterancesCommand(self, self.text_widget, self.waveform_widget, segments_id))



    def autoAlignSentences(self, sentences: List[str], range: Optional[Segment] = None) -> List[Segment]:
        text = "|| " + " || ".join(sentences) + " || "
        
        if range:
            tokens = self.getTranscriptionForSegment(range[0], range[1])
        else:
            tokens = self.media_metadata.get("transcription", [])

        alignment = align_text_with_vosk_tokens(text, tokens)

        # Separating into segments
        segments = []
        segment_tokens = []
        for al in alignment:
            if al[0] is None:
                continue
            if al[0] == "||":
                # print("||")
                if segment_tokens:
                    # print(segment_tokens[0])
                    # print(segment_tokens[-1])
                    first_idx = 0
                    last_idx = len(segment_tokens) - 1
                    first_token = segment_tokens[first_idx][1]
                    last_token = segment_tokens[last_idx][1]
                    # Skip first tokens if they align to None
                    while (first_token is None) and (first_idx < last_idx):
                        first_idx += 1
                        first_token = segment_tokens[first_idx][1]
                    # Skip last tokens if they align to None
                    while (last_token is None) and (first_idx < last_idx):
                        last_idx -= 1
                        last_token = segment_tokens[last_idx][1]

                    print(f"{first_token=} {last_token=}")
                    if not (first_token or last_token):
                        segments.append(None)
                        continue
                    
                    if first_token:
                        segment_start = first_token[1]
                    else:
                        segment_start = last_token[1]
                    
                    if last_token:
                        segment_end = last_token[2]
                    else:
                        segment_end = first_token[2]
                    
                    segments.append([segment_start, segment_end])
                    segment_tokens.clear()
                continue
            segment_tokens.append(al)
        return segments


class Block:
    def __init__(self, parent: DocumentController) -> None:
        self.parent = parent
        self.segment: Segment = []
        self.segment_id: SegmentId = -1