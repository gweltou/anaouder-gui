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

from typing import List, Tuple, Dict, Optional, Iterator
import logging
from pathlib import Path
from copy import deepcopy

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
from src.waveform_widget import WaveformWidget, Handle
from src.interfaces import MyTextBlockUserData
from src.utils import (
    LINE_BREAK,
    extract_sentence_regions,
    yellow
)
from src.commands import (
    AddSegmentCommand, DeleteSegmentsCommand, ResizeSegmentCommand,
    DeleteUtterancesCommand, JoinUtterancesCommand,
    InsertBlockCommand,
    MoveTextCursor,
)
from src.aligner import (
    smart_split_text, smart_split_time,
    SmartSplitError
)
from src.cache_system import cache
from src.strings import app_strings
from src.services.logger import logger



class DocumentController(QObject):
    message = Signal(str)
    refresh_segment_info = Signal(int)

    def __init__(self, parent: QObject|None = None) -> None:
        super().__init__(parent)

        self.media_path: Path|None = None
        self.segments: Dict[SegmentId, Segment] = dict()
        self._sorted_segments = []

        self.text_widget: TextEditWidget|None = None
        self.waveform_widget: WaveformWidget|None = None

        self.must_sort = False
        self.id_counter = 0
        self.undo_stack = QUndoStack(parent)

        self.memoized_segment = None # Memoized transcription for one segment
        self.memoized_transcription_tokens = []
    

    def clear(self) -> None:
        """ Clears the document """
        # self.media_path = None
        self.segments.clear()
        self.id_counter = 0
        self.must_sort = True

        if self.waveform_widget:
            self.waveform_widget.must_redraw = True
        
        # Clear text document
        if self.text_widget is not None:
            self.text_widget.document().clear()
            self.text_widget.updateLineNumberAreaWidth()
            self.text_widget.updateLineNumberArea()
        
        self.undo_stack.clear()


    def setTextWidget(self, text_widget: TextEditWidget) -> None:
        self.text_widget = text_widget
        self.text_widget.join_utterances.connect(self.joinUtterances)
        self.text_widget.delete_utterances.connect(self.deleteUtterances)
        self.text_widget.split_utterance.connect(self.splitFromText)
        # self.text_widget.request_auto_align.connect(self.autoAlignSelectedBlocks)
    

    def setWaveformWidget(self, waveform_widget: WaveformWidget) -> None:
        self.waveform_widget = waveform_widget
        self.waveform_widget.join_utterances.connect(self.joinUtterances)
        self.waveform_widget.delete_utterances.connect(self.deleteUtterances)
        self.waveform_widget.delete_segments.connect(self.deleteSegments)
        self.waveform_widget.split_utterance.connect(self.splitFromWaveform)
    

    def setMediaPath(self, media_path: Path | None) -> None:
        self.media_path = media_path
    

    def setDocumentPath(self, file_path: Path | None) -> None:
        self.document_path = file_path
        print(f"{self.document_path=}")


    def loadData(self, data: List[Tuple[str, Segment|None]]) -> None:
        """
        Load a document into the text widget and waveform widget.
        
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
    

    def getData(self) -> List[Tuple[str, Segment|None]]:
        assert self.text_widget is not None

        data = []

        block = self.text_widget.document().firstBlock()
        while block.isValid():
            text = self.getBlockHtml(block)
            utt_id = self.getBlockId(block)

            segment = None
            if utt_id != -1:
                segment = self.getSegment(utt_id)

            data.append( (text, segment) )
            block = block.next()

        return data


    def getDocumentState(self) -> dict:
        state = dict()
        cursor = self.text_widget.textCursor()
        state["cursor_position"] = cursor.position()
        state["cursor_anchor"] = cursor.anchor()
        # state["n_blocks"] = main_window.text_edit.document().blockCount()
        state["blocks"] = []
        block = self.text_widget.document().firstBlock()
        while block.isValid():
            text = block.text()[:]
            data = deepcopy(block.userData().data) if block.userData() else {}
            data.pop("density", None)
            state["blocks"].append((text, data))
            block = block.next()
        state["segments"] = deepcopy(self.segments)
        return state
    
    
    def getBlockByNumber(self, block_number: int) -> Optional[QTextBlock]:
        if self.text_widget is None:
            return None
        
        block = self.text_widget.document().findBlockByNumber(block_number)
        print(f"{block=}")
        return block


    def setBlockId(self, block: QTextBlock, segment_id: Optional[SegmentId]) -> None:
        """
        Set the segment id of a given block
        
        Args:
            block (QTextBlock)
            segment_id: SegmentId or None
        """
        logger.debug(f"setBlockId({block=}, {segment_id=})")
        if segment_id is None:
            block.setUserData(None)
        elif not block.userData():
            block.setUserData(MyTextBlockUserData({"seg_id": segment_id}))
        else:
            user_data = block.userData().data
            user_data["seg_id"] = segment_id
        
        self.text_widget.highlighter.rehighlightBlock(block)


    def getBlockId(self, block: QTextBlock) -> SegmentId:
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
            segment_id: SegmentId = user_data["seg_id"]
            if segment_id in self.segments:
                return BlockType.ALIGNED
        
        return BlockType.NOT_ALIGNED


    def getBlockHtml(self, block: QTextBlock) -> str | None:
        if self.text_widget is None:
            return None
        
        return self.text_widget.getBlockHtmlMap(block)[0]


    def getBlockMetadata(self, block: QTextBlock) -> Dict:
        metadata: MyTextBlockUserData = block.userData()
        if metadata:
            return metadata.data
        return dict()


    def setBlockMetadata(self, block: QTextBlock, metadata: dict | None) -> None:
        if metadata:
            block.setUserData(MyTextBlockUserData(metadata))
        else:
            block.setUserData(None)


    def updateBlockMetadata(self, block: QTextBlock, metadata: dict) -> None:
        block_metadata = self.getBlockMetadata(block)
        block_metadata.update(metadata)
        block.setUserData(MyTextBlockUserData(block_metadata))
        self.text_widget.highlighter.rehighlightBlock(block)


    def getNewSegmentId(self) -> SegmentId:
        """Returns the next available segment ID"""
        seg_id = self.id_counter
        self.id_counter += 1
        return seg_id
    

    def addSegment(self, segment: Segment, segment_id: Optional[SegmentId] = None) -> SegmentId:
        logger.debug(f"addSegment({segment=}, {segment_id=})")
        if segment_id is None:
            segment_id = self.getNewSegmentId()
        self.segments[segment_id] = segment

        self.must_sort = True
        self.waveform_widget.must_redraw = True
        return segment_id
        

    def getSegment(self, segment_id: SegmentId) -> Optional[Segment]:
        if segment_id in self.segments:
            return self.segments[segment_id]
        return None


    def updateSegment(self, segment_id: SegmentId, segment: Segment) -> None:
        """Updates a segment already present in document"""
        assert segment_id in self.segments
        self.segments[segment_id] = segment
        self.updateUtteranceDensity(segment_id)

        self.must_sort = True
        self.waveform_widget.must_redraw = True
        self.refresh_segment_info.emit(segment_id)


    def removeSegment(self, segment_id: SegmentId) -> None:
        assert segment_id in self.segments
        del self.segments[segment_id]
        self.must_sort = True
        self.waveform_widget.must_redraw = True

    
    def getSortedSegments(self) -> List[Tuple[SegmentId, Segment]]:
        """Return the list of (SegmentId, Segment), sorted by start time"""
        if self.must_sort:
            self._sorted_segments = sorted(self.segments.items(), key=lambda x: x[1])
            self.must_sort = False
        return self._sorted_segments


    def getPrevSegmentId(self, segment_id: SegmentId) -> SegmentId:
        """
        Returns the ID of the segment before the currently selected one, or -1.
        If no segment are selected, return the previous one relative to the playhead.

        Returns:
            A segment ID or -1
        """
        if segment_id is None:
            segment_id = self.active_segment_id
            
        sorted_segments = self.getSortedSegments()

        if segment_id == -1:
            # Check relative to playhead position
            for i, (seg_id, (start, _)) in enumerate(sorted_segments):
                if start > self.waveform_widget.playhead:
                    if i > 0:
                        return sorted_segments[i - 1][0]
                    return -1
        else:
            for i, (seg_id, _) in enumerate(sorted_segments):
                if seg_id == segment_id:
                    if i > 0:
                        return sorted_segments[i - 1][0]
                    return -1
        return -1


    def getNextSegmentId(self, segment_id: Optional[SegmentId] = None) -> SegmentId:
        """
        Returns the ID of the segment after the currently selected one, or -1.
        If no segment are selected, return the next one relative to the playhead.

        Returns:
            A segment ID or -1
        """
        if segment_id is None:
            segment_id = self.waveform_widget.active_segment_id

        sorted_segments = self.getSortedSegments()

        if segment_id == -1:
            # Check relative to playhead position
            for i, (segment_id, (_, end)) in enumerate(sorted_segments):
                if end > self.waveform_widget.playhead:
                    if i < len(sorted_segments) - 1:
                        return sorted_segments[i][0]
                    return -1
        else:
            for i, (seg_id, _) in enumerate(sorted_segments):
                if seg_id == segment_id:
                    if i < len(sorted_segments) - 1:
                        return sorted_segments[i + 1][0]
                    return -1
        return -1


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


    def getSegmentsAtTime(
        self,
        position_sec: float,
        onset = 0.0,
        offset = 0.0
    ) -> List[SegmentId]:
        """Return the list of IDs of all segment at a given positiont"""
        logger.debug(f"getSegmentAtTime({position_sec=})")
        segment_ids = []
        for segment_id, (start, end) in self.getSortedSegments():
            # Give precedence to the segment that starts at this timecode
            # rather than the one that ends at this timecode
            if start - 0.001 - onset <= position_sec < end + offset:
                segment_ids.append(segment_id)
            elif start - onset > position_sec:
                return segment_ids
        return segment_ids
    

    def getSegmentsAtTimeOffsets(
        self,
        position_sec: float,
        offsets: Dict[SegmentId, Tuple]
    ) -> List[SegmentId]:
        """Return the list of IDs of all segment at a given positiont"""
        logger.debug(f"getSegmentAtTime({position_sec=})")
        segment_ids = []
        for segment_id, (start, end) in self.getSortedSegments():
            # Give precedence to the segment that starts at this timecode
            # rather than the one that ends at this timecode
            onset, offset = offsets.get(segment_id, (0.0, 0.0))
            if start - onset <= position_sec < end + offset:
                segment_ids.append(segment_id)
            elif start - onset > position_sec:
                return segment_ids
        return segment_ids
    

    def getTextById(self, segment_id: SegmentId) -> str | None:
        block = self.getBlockById(segment_id)
        if block is None:
            return None
        return block.text()
    

    def getAllBlocks(self) -> Iterator[QTextBlock]:
        block = self.text_widget.document().firstBlock()
        while block.isValid():
            yield block
            block = block.next()


    def getUtteranceDensity(self, segment_id: SegmentId) -> float:
        """Get the density (chars/s) field of an utterance"""
        logger.debug(f"getUtteranceDensity({segment_id=})")

        if self.waveform_widget is None:
            return 0.0
        
        # If resizing, return the uncommited resizing density
        if self.waveform_widget.resizing_handle and self.waveform_widget.active_segment_id == segment_id:
            return self.waveform_widget.resizing_density

        block = self.getBlockById(segment_id)
        if not block:
            logger.warning("No block found for id: {seg_id}")
            return 0.0
        
        block_metadata = block.userData().data
        if "density" not in block_metadata:
            self.updateUtteranceDensity(segment_id)

        return block_metadata.get("density", 0.0)
    

    def updateUtteranceDensity(self, segment_id: SegmentId) -> None:
        """Update the density (chars/s) field of an utterance"""
        logger.debug(f"updateUtteranceDensity({segment_id=})")
        assert self.text_widget is not None
                
        block = self.getBlockById(segment_id)
        if block is None:
            return

        # Count the number of characters in sentence
        num_chars = self.getSentenceLength(block)

        segment = self.getSegment(segment_id)
        if not segment:
            return
        
        start, end = segment
        dur = end - start
        if dur > 0.0:
            new_density = num_chars / dur
            # current_density = block.userData().data.get("density", -1.0)
            block.userData().data["density"] = new_density


    def getSentenceLength(self, block: QTextBlock) -> int:
        """Returns length of sentence, stripped of metadata and comments"""
        if not block:
            return 0.0
        sentence_splits = extract_sentence_regions(block.text())
        return sum([ e-s for s, e in sentence_splits ], 0)


    def cropHead(self) -> None:
        logger.debug("cropHead")
        if self.waveform_widget is None:
            return
        
        active_segment_id = self.waveform_widget.active_segment_id
        playhead = self.waveform_widget.playhead
        
        if segment := self.getSegment(active_segment_id):
            if playhead < segment[1]:
                # Stop at the previous segment
                prev_segment_id = self.getPrevSegmentId(active_segment_id)
                if prev_segment := self.getSegment(prev_segment_id):
                    playhead = max(playhead, prev_segment[1])

                self.undo_stack.push(
                    ResizeSegmentCommand(
                        self,
                        active_segment_id,
                        playhead,
                        segment[1]
                    )
                )
        elif self.waveform_widget.selection_is_active:
            self.waveform_widget.resizeSelection(playhead, Handle.LEFT)


    def cropTail(self) -> None:
        logger.debug("cropTail")
        if self.waveform_widget is None:
            return
        
        active_segment_id = self.waveform_widget.active_segment_id
        playhead = self.waveform_widget.playhead
        
        if segment := self.getSegment(active_segment_id):
            if playhead > segment[0]:
                # Stop at the next segment
                next_segment_id = self.getNextSegmentId(active_segment_id)
                if next_segment := self.getSegment(next_segment_id):
                    playhead = min(playhead, next_segment[0])
                
                self.undo_stack.push(
                    ResizeSegmentCommand(
                        self,
                        active_segment_id,
                        segment[0],
                        playhead
                    )
                )
        elif self.waveform_widget.selection_is_active:
            self.waveform_widget.resizeSelection(playhead, Handle.RIGHT)


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

        seg_ids = self.getSegmentsAtTime(position_sec)
        if not seg_ids:
            return (-1, "")
        seg_id = seg_ids[0]
        
        # Remove metadata from subtitle text
        block = self.getBlockById(seg_id)
        if block is None:
            return (-1, "")

        html, _ = self.text_widget.getBlockHtmlMap(block)
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

        cached_transcription = cache.get_media_transcription(self.media_path) if self.media_path else None
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
                text = self.text_widget.getBlockHtmlMap(block)[0]

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
        logger.debug(f"splitFromText({segment_id=}, {position=})")

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
        cached_transcription = cache.get_media_transcription(self.media_path) if self.media_path else None
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
                    logger.debug('"Smart" splitting')
                    left_seg, right_seg = smart_split_text(text, position, tokens_range)
                    left_seg[0] = seg_start
                    right_seg[1] = seg_end
                except SmartSplitError as e:
                    logger.warning(e)
                    self.message.emit(app_strings.TR_CANT_SMART_SPLIT + f": {e}")
                except Exception as e:
                    logger.warning(e)
                    self.message.emit(app_strings.TR_CANT_SMART_SPLIT + f": {e}")

        if not left_seg or not right_seg:
            # Revert to naive splitting method
            dur = seg_end - seg_start
            pc = position / len(text)
            left_seg = [seg_start, seg_start + dur*pc - 0.05]
            right_seg = [seg_start + dur*pc + 0.05, seg_end]
            logger.debug("Ratio splitting")
        
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
        cached_transcription = cache.get_media_transcription(self.media_path) if self.media_path else None
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
                    logger.debug("smart splitting")
                    left_text, right_text = smart_split_time(text, timepos, tokens_range)
                except Exception as e:
                    self.message.emit(app_strings.TR_CANT_SMART_SPLIT)
                    logger.error(f"Could not smart split: {e}")

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
        self.undo_stack.push(
            DeleteUtterancesCommand(
                self,
                self.text_widget,
                self.waveform_widget,
                [seg_id]
            )
        )
        self.undo_stack.push(
            AddSegmentCommand(
                self,
                self.waveform_widget,
                left_seg,
                left_id
            )
        )
        print(f"{self.text_widget.textCursor().position()=}")
        self.undo_stack.push(
            InsertBlockCommand(
                self,
                self.text_widget,
                self.text_widget.textCursor().position(),
                seg_id = left_id,
                text = left_text,
                after = True
            )
        )
        self.undo_stack.push(AddSegmentCommand(self, self.waveform_widget, right_seg, right_id))
        self.undo_stack.push(
            InsertBlockCommand(
                self,
                self.text_widget,
                self.text_widget.textCursor().position(),
                seg_id = right_id,
                text = right_text,
                after = True
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


    def joinUtterances(self, segment_ids) -> None:
        """
        Join many segments in one.
        Keep the segment ID of the earliest segment among the selected ones.
        """
        if self.text_widget is None or self.waveform_widget is None:
            return
        
        self.undo_stack.push(JoinUtterancesCommand(self, self.text_widget, self.waveform_widget, segment_ids))


    def getSelectedBlocksAndTimeRange(self) -> Tuple[List[QTextBlock], List] | None:
        """Returns the selected text blocks and the corresponding time range"""
        logger.debug("autoAlignSelectedBlocks()")

        if self.text_widget is None or self.waveform_widget is None:
            return
        
        start_range = 0.0
        end_range = self.waveform_widget.audio_len

        cursor = self.text_widget.textCursor()

        # Find the range of non-aligned blocks to align
        # Stop at first aligned block, if there is any in the cursor selection
        to_align: List[QTextBlock] = []

        if cursor.hasSelection():
            block = self.text_widget.findBlock(cursor.selectionStart())
            end_block = self.text_widget.findBlock(cursor.selectionEnd())
            assert (block is not None) and (end_block is not None)
            assert (block.blockNumber() <= end_block.blockNumber())

            while block.isValid() and block is not end_block:
                block_type = self.getBlockType(block)
                if block_type is BlockType.NOT_ALIGNED:
                    to_align.append(block)
                elif block_type == BlockType.ALIGNED:
                    break
                block = block.next()
        else:
            block = cursor.block()
            block_type = self.getBlockType(block)
            if block_type is BlockType.NOT_ALIGNED:
                to_align.append(block)
        
        if not to_align:
            return

        # Find previous aligned block to get the audio range start time
        block = to_align[0].previous()
        while block.isValid():
            block_type = self.getBlockType(block)
            if block_type is BlockType.ALIGNED:
                block_id = self.getBlockId(block)
                block_segment = self.getSegment(block_id)
                if block_segment is not None:
                    start_range = block_segment[1]
                    break
            block = block.previous()
        
        # Find next aligned block to get the audio range end time
        block = to_align[-1].next()
        while block.isValid():
            block_type = self.getBlockType(block)
            if block_type is BlockType.ALIGNED:
                block_id = self.getBlockId(block)
                block_segment = self.getSegment(block_id)
                if block_segment is not None:
                    end_range = block_segment[0]
                    break
            block = block.next()
        
        time_range = [start_range, end_range]
        
        return (to_align, time_range)


    def deleteUtterances(self, segment_ids: List[SegmentId]) -> None:
        """Delete both segments and sentences"""
        if (self.text_widget is None) or (self.waveform_widget is None):
            return
        
        if segment_ids:
            if self.waveform_widget.active_segment_id in segment_ids:
                self.refresh_segment_info.emit(-1)
            self.undo_stack.push(DeleteUtterancesCommand(self, self.text_widget, self.waveform_widget, segment_ids))
        else:
            self.message.emit(self.tr("Select one or more utterances first"))


    def deleteSegments(self, segments_id: List[SegmentId]) -> None:
        """Delete segments but keep sentences"""
        self.undo_stack.push(DeleteSegmentsCommand(self, self.text_widget, self.waveform_widget, segments_id))


    def selectAll(self) -> None:
        selection = [ id for id, _ in self.getSortedSegments() ]
        self.waveform_widget.active_segments = selection
        self.waveform_widget.active_segment_id = selection[-1] if selection else -1
        self.waveform_widget.must_redraw = True