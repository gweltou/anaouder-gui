from dataclasses import dataclass
from math import ceil

from PySide6.QtCore import (
    QPoint,
    QRect,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap

from src.interfaces import DocumentInterface, Segment
from src.strings import app_strings
from src.ui.waveform.data import Handle, ResizeState, SubtitleRules, WaveformData


@dataclass
class PenSet:
    # Inactive segments
    inactive_pen: QPen
    inactive_brush: QBrush

    # Active segments
    active_pen: QPen
    active_shadow_pen: QPen
    active_brush: QBrush

    # Selection (active state)
    selection_pen: QPen
    selection_shadow_pen: QPen
    selection_brush: QBrush

    # Selection (inactive state)
    selection_inactive_pen: QPen
    selection_inactive_brush: QBrush

    # Handles
    handle_left_pen: QPen
    handle_right_pen: QPen
    handle_middle_pen: QPen
    handle_middle_shadow_pen: QPen

    # Snapping markers
    marker_pen: QPen

    wf_pen: QPen
    timeline_pen: QPen
    wf_progress: QBrush

    # Playhead
    playhead_pen: QPen
    playhead_pen_shadow: QPen

    @classmethod
    def from_theme(cls, theme) -> "PenSet":
        def pen(r, g, b, a=255, width=1) -> QPen:
            p = QPen(QColor(r, g, b, a), width)
            return p

        def round_pen(r, g, b, a=255, width=1) -> QPen:
            p = QPen(QColor(r, g, b, a), width)
            p.setCapStyle(Qt.PenCapStyle.RoundCap)
            return p

        def brush(r, g, b, a=255) -> QBrush:
            return QBrush(QColor(r, g, b, a))

        seg = theme.colors.segment_green
        sel = theme.colors.selection_blue

        return cls(
            inactive_pen=pen(*seg.getRgb()[:3], a=100),
            inactive_brush=brush(*seg.getRgb()[:3], a=40),
            active_pen=pen(*seg.getRgb()[:3], a=255),
            active_shadow_pen=pen(*seg.getRgb()[:3], a=60, width=3),
            active_brush=brush(*seg.getRgb()[:3], a=50),
            selection_pen=pen(*sel.getRgb()[:3], a=255),
            selection_shadow_pen=pen(*sel.getRgb()[:3], a=60, width=3),
            selection_brush=brush(*sel.getRgb()[:3], a=50),
            selection_inactive_pen=pen(110, 180, 240),
            selection_inactive_brush=brush(110, 180, 240, 40),
            handle_left_pen=round_pen(255, 80, 80, a=255, width=2),
            handle_right_pen=round_pen(80, 255, 80, a=255, width=2),
            handle_middle_pen=round_pen(255, 240, 60, width=2),
            handle_middle_shadow_pen=round_pen(255, 240, 60, a=80, width=5),
            marker_pen=pen(120, 120, 120),
            wf_pen=pen(0, 162, 180),
            timeline_pen=pen(*theme.colors.wf_timeline.getRgb()[:3]),
            wf_progress=brush(*theme.colors.wf_progress.getRgb()[:3]),
            playhead_pen=pen(255, 20, 20, a=100),
            playhead_pen_shadow=pen(255, 20, 20, a=40, width=3),
        )


@dataclass(frozen=True)
class LayoutMetrics:
    """Recomputed only on resize."""

    timecode_margin: int
    active_top: int
    active_height: int
    inactive_top: int
    inactive_height: int
    selection_top: int
    selection_height: int
    inactive_selection_top: int
    inactive_selection_height: int

    segment_handle_top: int
    segment_handle_down: int
    wf_mid_y: int  # vertical center of waveform

    @classmethod
    def compute(cls, widget_width: int, widget_height: int) -> "LayoutMetrics":
        timecode_margin = 20  # Margin above waveform zone
        wf_h = widget_height - timecode_margin

        active_seg_frac = 0.56
        inactive_seg_frac = 0.48
        active_selection_frac = 0.64
        inactive_selection_frac = 0.60

        top_handle_frac = 0.16
        bottom_handle_frac = 0.84

        def top(frac: float) -> int:
            """
            Returns the top coordinate from a fractional size
            relative to the waveform area height.
            """
            return round(timecode_margin + (1.0 - frac) * 0.5 * wf_h)

        def height(frac: float) -> int:
            return round(frac * wf_h)

        return cls(
            timecode_margin=timecode_margin,
            active_top=top(active_seg_frac),
            active_height=height(active_seg_frac),
            inactive_top=top(inactive_seg_frac),
            inactive_height=height(inactive_seg_frac),
            selection_top=top(active_selection_frac),
            selection_height=height(active_selection_frac),
            inactive_selection_top=top(inactive_selection_frac),
            inactive_selection_height=height(inactive_selection_frac),
            segment_handle_top=round(timecode_margin + wf_h * top_handle_frac),
            segment_handle_down=round(timecode_margin + wf_h * bottom_handle_frac),
            wf_mid_y=round(timecode_margin + 0.5 * wf_h),
        )


@dataclass(frozen=True)
class RenderContext:
    """Rebuilt every frame."""

    t_left: float
    t_right: float
    ppsec: float
    width: int
    height: int
    audio_len: float
    time_offset: float
    fps: float
    playhead: float
    recognizer_progress: float
    active_segments: list
    active_segment_id: int
    resizing_state: ResizeState
    handle_state: list
    selection: Segment | None
    selection_is_active: bool
    display_scene_change: bool
    scenes: list
    layout: LayoutMetrics
    palette: PenSet

    def t_to_x(self, t: float) -> int:
        """Convert a timecode to a pixel x position."""
        return round((t - self.t_left) * self.ppsec)

    def x_to_t(self, x: float) -> float:
        return self.t_left + x / self.ppsec


class RenderLayer:
    def draw(self, painter: QPainter, ctx: RenderContext): ...


class ProgressLayer(RenderLayer):
    def draw(self, painter: QPainter, ctx: RenderContext) -> None:
        if ctx.recognizer_progress < ctx.t_left:
            return

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ctx.palette.wf_progress)
        w = (ctx.recognizer_progress - ctx.t_left) * ctx.ppsec
        painter.drawRect(QRect(0, 0, int(w), ctx.height))


class WaveformLayer(RenderLayer):
    SCALE_Y = 3.5

    def __init__(self, scaled_waveform: WaveformData):
        self._waveform = scaled_waveform

        # Cache: only recompute when zoom changes, not on scroll
        self._cache: QPixmap | None = None
        self._cache_ppsec: float = -1.0
        self._cache_t_left: float = 0.0
        self._cache_width: int = 0

    def invalidate(self) -> None:
        """Call when audio data or zoom changes."""
        self._cache = None

    def draw(self, painter: QPainter, ctx: RenderContext) -> None:
        pix_per_sample = ctx.ppsec / self._waveform.sr
        if pix_per_sample > 1.0:
            # Zoomed in far enough to see individual samples —
            # cache is not useful here, just draw directly
            self._draw_direct(painter, ctx)
            return

        if self._cache_needs_rebuild(ctx):
            self._rebuild_cache(ctx)

        # Blit the relevant horizontal slice of the cache
        assert self._cache is not None
        src_x = round((ctx.t_left - self._cache_t_left) * ctx.ppsec)
        painter.drawPixmap(0, 0, self._cache, src_x, 0, ctx.width, ctx.height)

    def _cache_needs_rebuild(self, ctx: RenderContext) -> bool:
        if self._cache is None:
            return True
        if ctx.ppsec != self._cache_ppsec:
            return True
        # Rebuild if the view has scrolled outside the cached region
        cache_t_right = self._cache_t_left + self._cache_width / ctx.ppsec
        margin = ctx.width / ctx.ppsec  # one viewport-width of lookahead
        if ctx.t_left < self._cache_t_left + margin * 0.1:
            return True
        if ctx.t_right > cache_t_right - margin * 0.1:
            return True
        return False

    def _rebuild_cache(self, ctx: RenderContext) -> None:
        """
        Render a pixmap 3x the viewport width, centered on the current view.
        This means we can scroll ~1 viewport left or right before needing a rebuild.
        """
        margin = ctx.width / ctx.ppsec  # 1 viewport in seconds
        cache_t_left = max(0.0, ctx.t_left - margin)
        cache_width = ctx.width * 3

        chart = self._waveform.get(cache_t_left, cache_width)

        self._cache = QPixmap(cache_width, ctx.height)
        self._cache.fill(Qt.GlobalColor.transparent)

        p = QPainter(self._cache)
        p.setPen(ctx.palette.wf_pen)
        lyt = ctx.layout
        wf_h = ctx.height - lyt.timecode_margin

        for x in range(cache_width):
            ymin = round(lyt.timecode_margin + wf_h * (0.5 + self.SCALE_Y * chart[x]))
            ymax = round(
                lyt.timecode_margin
                + wf_h * (0.5 + self.SCALE_Y * chart[x + cache_width])
            )
            p.drawLine(x, ymin, x, ymax)

        p.end()

        self._cache_ppsec = ctx.ppsec
        self._cache_t_left = cache_t_left
        self._cache_width = cache_width

    def _draw_direct(self, painter: QPainter, ctx: RenderContext) -> None:
        """Used when zoomed in far enough that individual samples are visible."""
        chart = self._waveform.get(ctx.t_left, ctx.width)
        painter.setPen(ctx.palette.wf_pen)
        lyt = ctx.layout
        wf_h = ctx.height - lyt.timecode_margin

        for x in range(ctx.width):
            ymin = round(lyt.timecode_margin + wf_h * (0.5 + self.SCALE_Y * chart[x]))
            ymax = round(
                lyt.timecode_margin + wf_h * (0.5 + self.SCALE_Y * chart[x + ctx.width])
            )
            painter.drawLine(x, ymin, x, ymax)


class SegmentsLayer(RenderLayer):
    def __init__(
        self,
        document_controller: DocumentInterface,
        subtitle_rules: SubtitleRules,
    ) -> None:
        self._doc = document_controller
        self._rules = subtitle_rules

    def draw(self, painter: QPainter, ctx: RenderContext) -> None:
        self._draw_inactive_segments(painter, ctx)
        self._draw_selection(painter, ctx)
        self._draw_active_segments(painter, ctx)

    def _draw_inactive_segments(self, painter: QPainter, ctx: RenderContext) -> None:
        use_pen = ctx.ppsec > 4

        for id, (start, end) in self._doc.segments.items():
            if id in ctx.active_segments:
                continue
            if end <= ctx.t_left or start >= ctx.t_right:
                continue
            if (end - start) * ctx.ppsec < 1:
                continue

            x = ctx.t_to_x(start)
            w = round((end - start) * ctx.ppsec)

            if use_pen:
                painter.setPen(ctx.palette.inactive_pen)
            else:
                painter.setPen(Qt.PenStyle.NoPen)

            painter.setBrush(ctx.palette.inactive_brush)
            painter.drawRect(x, ctx.layout.inactive_top, w, ctx.layout.inactive_height)

    def _draw_selection(self, painter: QPainter, ctx: RenderContext) -> None:
        if ctx.selection is None:
            return

        start, end = ctx.selection
        if end <= ctx.t_left or start >= ctx.t_right:
            return

        x = ctx.t_to_x(start)
        w = round((end - start) * ctx.ppsec)
        lyt = ctx.layout

        if ctx.selection_is_active:
            # Backround
            painter.setPen(ctx.palette.selection_shadow_pen)
            painter.setBrush(ctx.palette.selection_brush)
            painter.drawRect(QRect(x, lyt.selection_top, w, lyt.selection_height))
            # Foreground
            painter.setPen(ctx.palette.selection_pen)
            painter.setBrush(QBrush())
            painter.drawRect(QRect(x, lyt.selection_top, w, lyt.selection_height))
            self._draw_handles_for_bounds(
                painter, ctx, start, end, x, w, is_selection=True
            )
        else:
            painter.setBrush(ctx.palette.selection_inactive_brush)
            painter.setPen(ctx.palette.selection_inactive_pen)
            painter.drawRect(
                QRect(x, lyt.inactive_selection_top, w, lyt.inactive_selection_height)
            )

    def _draw_active_segments(self, painter: QPainter, ctx: RenderContext) -> None:
        for seg_id in ctx.active_segments:
            if seg_id not in self._doc.segments:
                continue

            start, end = self._resolve_bounds(seg_id, ctx)

            if end <= ctx.t_left and start >= ctx.t_right:
                continue

            x = ctx.t_to_x(start)
            w = round((end - start) * ctx.ppsec)
            lyt = ctx.layout

            painter.setPen(ctx.palette.active_shadow_pen)
            painter.setBrush(ctx.palette.active_brush)
            painter.drawRect(QRect(x, lyt.active_top, w, lyt.active_height))
            painter.setPen(ctx.palette.active_pen)
            painter.setBrush(QBrush())
            painter.drawRect(QRect(x, lyt.active_top, w, lyt.active_height))

            self._draw_handles_for_bounds(
                painter, ctx, start, end, x, w, is_selection=False
            )

        # Snapping markers: only for the primary active segment, right handle drag
        if (
            ctx.resizing_state.handle == Handle.RIGHT
            and ctx.active_segment_id >= 0
            and ctx.fps > 0
        ):
            self._draw_snapping_markers(painter, ctx)

    def _resolve_bounds(self, seg_id: int, ctx: RenderContext) -> Segment:
        """Return the visual bounds for a segment, accounting for an active resize."""
        rs = ctx.resizing_state
        if (
            seg_id == ctx.active_segment_id
            and rs.handle is not None
            and rs.segment is not None
        ):
            return rs.segment
        return self._doc.segments[seg_id]

    def _draw_handles_for_bounds(
        self,
        painter: QPainter,
        ctx: RenderContext,
        start: float,
        end: float,
        x: int,
        w: int,
        is_selection: bool,
    ) -> None:
        """
        Draw whichever handle is active for a given segment or selection.
        Exactly one handle is drawn per call (left, right, or middle).
        If no handle is hovered/dragged, the middle handle is drawn passively.
        """
        rs = ctx.resizing_state
        hs = ctx.handle_state  # [left_hot, mid_hot, right_hot]

        left_active = hs[0] or rs.handle == Handle.LEFT
        right_active = hs[2] or rs.handle == Handle.RIGHT
        mid_active = hs[1] or rs.handle == Handle.MIDDLE

        middle_t = start + (end - start) / 2
        mid_x = ctx.t_to_x(middle_t)

        if left_active:
            self._draw_left_handle(painter, ctx, x)
        elif right_active:
            self._draw_right_handle(painter, ctx, x + w)
        elif mid_active:
            self._draw_middle_handle(painter, ctx, mid_x, active=True)
        else:
            # Passive middle handle: only for single active segment or active selection
            single = len(ctx.active_segments) == 1
            if single or is_selection:
                self._draw_middle_handle(painter, ctx, mid_x, active=False)

    def _draw_left_handle(self, painter: QPainter, ctx: RenderContext, x: int) -> None:
        lyt = ctx.layout
        painter.setPen(ctx.palette.handle_left_pen)
        painter.drawLine(x, lyt.segment_handle_top, x, lyt.segment_handle_down)
        painter.drawLine(x - 3, lyt.segment_handle_top, x, lyt.segment_handle_top)
        painter.drawLine(x - 3, lyt.segment_handle_down, x, lyt.segment_handle_down)

    def _draw_right_handle(self, painter: QPainter, ctx: RenderContext, x: int) -> None:
        lyt = ctx.layout
        painter.setPen(ctx.palette.handle_right_pen)
        painter.drawLine(x, lyt.segment_handle_top, x, lyt.segment_handle_down)
        painter.drawLine(x, lyt.segment_handle_top, x + 3, lyt.segment_handle_top)
        painter.drawLine(x, lyt.segment_handle_down, x + 3, lyt.segment_handle_down)

    def _draw_middle_handle(
        self, painter: QPainter, ctx: RenderContext, x: int, active: bool
    ) -> None:
        lyt = ctx.layout
        mid_y = lyt.wf_mid_y
        radius = 12 if active else 10

        def draw_shapes():
            painter.drawEllipse(QPoint(x, mid_y), radius, radius)
            if active:
                for sign in (-1, 1):
                    tip_x = x + sign * (round(1.5 * radius) + radius // 2)
                    base_x = x + sign * round(1.5 * radius)
                    painter.drawLine(base_x, mid_y - radius // 2, tip_x, mid_y)
                    painter.drawLine(base_x, mid_y + radius // 2, tip_x, mid_y)

        if active:
            painter.setPen(ctx.palette.handle_middle_shadow_pen)
            draw_shapes()
            painter.setPen(ctx.palette.handle_middle_pen)
            draw_shapes()
        else:
            shadow_pen = (
                ctx.palette.selection_shadow_pen
                if ctx.selection_is_active
                else ctx.palette.active_shadow_pen
            )
            base_pen = (
                ctx.palette.selection_pen
                if ctx.selection_is_active
                else ctx.palette.active_pen
            )
            painter.setPen(shadow_pen)
            draw_shapes()
            painter.setPen(base_pen)
            draw_shapes()

    def _draw_snapping_markers(self, painter: QPainter, ctx: RenderContext) -> None:
        seg_id = ctx.active_segment_id
        start, end = self._doc.segments[seg_id]
        current_dur = end - start
        fps = ctx.fps
        rules = self._rules
        rs = ctx.resizing_state
        lyt = ctx.layout

        marker_top = round(
            lyt.timecode_margin + (ctx.height - lyt.timecode_margin) * 0.15
        )
        marker_down = round(
            lyt.timecode_margin + (ctx.height - lyt.timecode_margin) * 0.85
        )

        markers: list[tuple[float, str, int]] = []  # (timecode, label, y_offset)

        # --- Right boundary of the previous segment (min interval) ---
        next_id = self._doc.getNextSegmentId(seg_id)
        if next_id != -1:
            next_boundary = self._doc.segments[next_id][0] - rules.min_interval / fps
        else:
            next_boundary = None  # no constraint from the right

        # --- Minimum duration ---
        min_dur = rules.min_frames / fps
        if current_dur < min_dur:
            markers.append((start + min_dur, "min", 2))

        # --- Maximum duration / next segment boundary ---
        max_dur = rules.max_frames / fps
        if next_boundary is not None and next_boundary < start + max_dur:
            markers.append((next_boundary, "next", 2))
        else:
            markers.append((start + max_dur, "max", 1))

        # --- Ideal density ---
        if rs.textlen > 0 and rules.target_density > 0:
            ideal_dur = rs.textlen / rules.target_density
            label = f"{round(rules.target_density, 1)} c/s"
            markers.append((start + ideal_dur, label, -6))

        # Draw
        painter.setPen(ctx.palette.marker_pen)
        for t, label, y_off in markers:
            mx = ctx.t_to_x(t)
            painter.drawLine(mx, marker_top, mx, marker_down)
            painter.drawText(
                mx - 4 * len(label),
                round(ctx.height * 0.15) + 15 + y_off,
                label,
            )


class TimelineLayer(RenderLayer):
    def draw(self, painter: QPainter, ctx: RenderContext) -> None:
        """Paint timeline tics and text"""

        # Account for the timecode offset in the video metadata
        t_left = ctx.t_left + ctx.time_offset
        t_right = ctx.t_right + ctx.time_offset

        if ctx.ppsec > 50:
            time_step = 1
        elif ctx.ppsec > 6:
            time_step = 10
        elif ctx.ppsec > 1.8:
            time_step = 30
        elif ctx.ppsec > 0.5:
            time_step = 60
        else:
            time_step = 300  # Every 5 min

        painter.setPen(ctx.palette.timeline_pen)

        # Video frames timecodes
        if ctx.fps > 0 and time_step == 1:
            frame_time_step = 1.0 / ctx.fps
            t = ceil(t_left / frame_time_step) * frame_time_step
            while t < t_right:
                t += frame_time_step
                t_x = round((t - t_left) * ctx.ppsec)
                painter.drawLine(
                    t_x, ctx.layout.timecode_margin - 4, t_x, ctx.layout.timecode_margin
                )

        if time_step == 10:
            # Draw a tick for every seconds
            ti = ceil(max(0.0, t_left))
            for t in range(ti, int(t_right) + 1, 1):
                t_x = round((t - t_left) * ctx.ppsec)
                painter.drawLine(
                    t_x, ctx.layout.timecode_margin, t_x, ctx.layout.timecode_margin + 4
                )

        # Draw an extra tick at every time step (zoom dependent)
        ti = ceil(max(0.0, t_left) / time_step) * time_step
        for t in range(ti, int(t_right) + 1, time_step):
            t_x = round((t - t_left) * ctx.ppsec)
            painter.drawLine(t_x, ctx.layout.timecode_margin, t_x, ctx.height - 4)
            minutes, secs = divmod(t, 60)
            hour, minutes = divmod(minutes, 60)

            if hour > 0:
                t_string = f"{hour}:{minutes:02}:{secs:02}"
            else:
                if secs == 0:
                    t_string = f"{minutes}{app_strings.TR_UNIT_MINUTE[0]}"
                elif minutes == 0:
                    t_string = f"{secs}{app_strings.TR_UNIT_SECOND}"
                else:
                    t_string = f"{minutes}{app_strings.TR_UNIT_MINUTE[0]}{secs:02}{app_strings.TR_UNIT_SECOND}"

            painter.drawText(t_x - 8 * len(t_string) // 2, 12, t_string)


class PlayheadLayer(RenderLayer):
    def draw(self, painter: QPainter, ctx: RenderContext) -> None:
        """Paint timeline tics and text"""

        if ctx.playhead < ctx.t_left or ctx.playhead > ctx.t_right:
            return

        t_x = ctx.t_to_x(ctx.playhead)
        painter.setPen(ctx.palette.playhead_pen_shadow)
        painter.drawLine(t_x, 0, t_x, ctx.height)
        painter.setPen(ctx.palette.playhead_pen)
        painter.drawLine(t_x, 0, t_x, ctx.height)


class SceneChangeLayer(RenderLayer):
    def draw(self, painter: QPainter, ctx: RenderContext) -> None:
        if not ctx.display_scene_change or not ctx.scenes:
            return

        height = 8
        sep_height = 12
        y_pos = ctx.height - height
        opacity = 200

        for i, (tc, r, g, b) in enumerate(ctx.scenes):
            if ctx.t_right < tc:
                break
            painter.setPen(Qt.PenStyle.NoPen)
            if ctx.t_left < tc:
                x = (tc - ctx.t_left) * ctx.ppsec
                if i > 0 and ctx.scenes[i - 1][0] <= ctx.t_left:
                    prev_color = ctx.scenes[i - 1][1:]
                    w = (tc - ctx.t_left) * ctx.ppsec
                    prev_color = ctx.scenes[i - 1][1:]
                    painter.setBrush(
                        QBrush(
                            QColor(prev_color[0], prev_color[1], prev_color[2], opacity)
                        )
                    )
                    painter.drawRect(QRect(0, y_pos, w, height))
                next_tc = (
                    ctx.scenes[i + 1][0] if i < len(ctx.scenes) - 1 else ctx.audio_len
                )
                w = (next_tc - tc) * ctx.ppsec
                painter.setBrush(QBrush(QColor(r, g, b, opacity)))
                painter.drawRect(QRect(x, y_pos, w, height))
                # Draw inter-scene lines
                painter.setPen(QPen(QColor(100, 100, 100)))
                painter.drawLine(x, ctx.height - sep_height, x, ctx.height)
            elif (
                tc < ctx.t_left
                and i < len(ctx.scenes) - 1
                and ctx.scenes[i + 1][0] > ctx.t_right
            ):
                painter.setBrush(QBrush(QColor(r, g, b, opacity)))
                painter.drawRect(QRect(0, y_pos, ctx.width, height))
