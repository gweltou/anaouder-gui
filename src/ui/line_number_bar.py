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

import math

from PySide6.QtCore import (
    QPoint,
    QRect,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QPainter,
    QPolygon,
)
from PySide6.QtWidgets import QWidget

from settings import QColor
from src.interfaces import DocumentInterface, TextEditorInterface
from src.ui.theme import theme
from src.utils import map_number


class LineNumberBar(QWidget):
    """Displays line numbers on the left of the text."""

    arrow_h = 8
    arrow_w = 20

    def __init__(
        self, editor: TextEditorInterface, document_controller: DocumentInterface
    ):
        super().__init__(editor)
        self.editor = editor
        self.document_controller = document_controller
        self.player_position = 0.0

    def updatePlayerPosition(self, time_s: float) -> None:
        self.player_position = time_s
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self.editor.getLineNumberAreaWidth(), 0)

    def _get_playhead(
        self,
        painter: QPainter,
        blocks_data: list[tuple],
        y_offset: int
    ) -> tuple[int, QRect | None]:
        """
        Highlight the background for the currently playing utterance
        and return playhead position

        Args:
            blocks_data: list of
                (block, top_y, bottom_y)
        Return:
            playhead's position (float)
        """
        t_pos = self.player_position
        width = self.width()
        height = self.height()

        playhead_y = 0
        last_end = 0.0
        last_bottom = -y_offset

        for block, top, bottom in blocks_data:
            segment_id = self.document_controller.getBlockId(block)
            segment = self.document_controller.getSegment(segment_id)
            if segment is None:
                continue
            start, end = segment

            if t_pos < start:
                # In between aligned segments
                playhead_y = round(map_number(t_pos, last_end, start, last_bottom, top))
                return playhead_y, None

            if start <= t_pos < end:
                # Playhead is over an utterance
                playhead_y = round(map_number(t_pos, start, end, top, bottom))
                block_rect = QRect(
                    0,
                    top,
                    width,
                    bottom - top,
                )
                return playhead_y, block_rect

            last_end = end
            last_bottom = bottom

        # Check if playhead is invisible down the current view
        if blocks_data:
            last_block = blocks_data[-1][0]
            segment_id = self.document_controller.getBlockId(last_block)
            segment = self.document_controller.getSegment(segment_id)
            assert segment is not None
            last_start, _ = segment

            if t_pos > last_start:
                playhead_y = height + 1

        return playhead_y, None

    def _paint_block_background(self, painter: QPainter, rect: QRect) -> None:
        painter.fillRect(
            rect,
            QColor(255, 0, 0, 40),
        )

    def _paint_playhead(self, painter: QPainter, playhead_y: int) -> None:
        height = self.height()
        width = self.width()
        half_width = width // 2

        # Draw playhead
        if 0 <= playhead_y <= height:
            # Line shadow
            painter.fillRect(
                QRect(
                    0,
                    playhead_y - 1,
                    width,
                    3,
                ),
                QColor(255, 0, 0, 60),
            )
            painter.setPen(QColor(255, 0, 0))
            painter.drawLine(0, playhead_y, width, playhead_y)
            return

        # Arrows animation
        t = self.player_position
        offset = round(2 * (math.sin(3 * math.pi * t) + 1) / 2) + 1

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 0, 0, 220))

        if playhead_y < 0:
            painter.drawPolygon(
                QPolygon(
                    [
                        QPoint(half_width, offset),
                        QPoint(half_width + self.arrow_w // 2, offset + self.arrow_h),
                        QPoint(half_width - self.arrow_w // 2, offset + self.arrow_h),
                    ]
                )
            )
        elif playhead_y > height:
            painter.drawPolygon(
                QPolygon(
                    [
                        QPoint(half_width - self.arrow_w // 2, height - self.arrow_h - offset),
                        QPoint(half_width + self.arrow_w // 2, height - self.arrow_h - offset),
                        QPoint(half_width, height - offset),
                    ]
                )
            )

    def paintEvent(self, event) -> None:
        """Paints the line numbers in the sidebar."""

        doc_layout = self.editor.document().documentLayout()

        aligned_block_tc = []  # Relative_pos and timecodes for each aligned block
        label_and_rect = []  # Block labels, text color and text bounding rects

        # Get the scrollbar offset (in pixels)
        offset_y = self.editor.verticalScrollBar().value()
        # page_bottom = offset_y + self.viewport().height()

        # Iterate over all text blocks (could be optimized)
        block = self.editor.document().begin()
        utterance_number = 0

        prev_block = None
        prev_block_top = 0
        prev_block_bottom = 0

        while block.isValid():
            rect = doc_layout.blockBoundingRect(block)

            is_aligned = False
            if self.editor.isAligned(block):
                utterance_number += 1
                is_aligned = True

            # Check if the block is visible in the viewport
            top_of_block = int(rect.top() - offset_y)
            bottom_of_block = int(rect.bottom() - offset_y)
            block_height = bottom_of_block - top_of_block

            if bottom_of_block >= 0 and top_of_block <= self.editor.viewport().height():
                if block.isVisible():
                    if is_aligned:
                        # Remember the last block before the first visible block
                        if prev_block is not None and len(aligned_block_tc) == 0 and top_of_block > 0:
                            aligned_block_tc.append(
                                (prev_block, prev_block_top, prev_block_bottom)
                            )

                        aligned_block_tc.append((block, top_of_block, bottom_of_block))
                        label_and_rect.append(
                            (
                                str(utterance_number),
                                Qt.GlobalColor.black,
                                QRect(0, top_of_block, self.width() - 4, block_height),
                            )
                        )

                    else:
                        label_and_rect.append(
                            (
                                "*",
                                Qt.GlobalColor.gray,
                                QRect(0, top_of_block, self.width() - 5, block_height),
                            )
                        )

            # Add the next utterance (outside of view)
            if top_of_block > self.editor.viewport().height() and is_aligned:
                aligned_block_tc.append((block, top_of_block, bottom_of_block))
                break

            prev_block = block
            prev_block_top = top_of_block
            prev_block_bottom = bottom_of_block
            block = block.next()

        # Render blocks left bar background
        painter = QPainter(self)
        painter.fillRect(event.rect(), theme.colors.line_number)

        playhead_y, block_bg_rect = self._get_playhead(painter, aligned_block_tc, offset_y)

        # Block background
        if block_bg_rect is not None:
            self._paint_block_background(painter, block_bg_rect)

        # Paint numbers
        for label, color, rect in label_and_rect:
            painter.setPen(color)
            painter.drawText(rect, Qt.AlignmentFlag.AlignRight, label)

        # Paint playhead or out of view arrows
        self._paint_playhead(painter, playhead_y)

        painter.end()

    def wheelEvent(self, event):
        self.editor.wheelEvent(event)
