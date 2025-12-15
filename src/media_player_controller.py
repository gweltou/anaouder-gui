"""
Media Player Controller Module

Handles all media playback operations
"""

import logging
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.interfaces import Segment, SegmentId
from src.cache_system import cache

# To trace the segmentation error when playing problematic segments
import faulthandler
faulthandler.enable()



log = logging.getLogger(__name__)



class PlaybackState:
    """Encapsulates the current playback state"""
    def __init__(self):
        self.playing_segment_id: SegmentId = -1
        self.looping: bool = False
        self.is_playing: bool = False
        self.current_position: float = 0.0  # in seconds
        
    def reset(self):
        """Reset to initial state"""
        self.playing_segment_id = -1
        self.is_playing = False
        self.current_position = 0.0



class MediaPlayerController(QObject):
    """
    Handles all media playback operations.
    
    Signals:
        position_changed: Emitted when playback position changes (position_sec: float)
        playback_started: Emitted when playback starts
        playback_stopped: Emitted when playback stops
        segment_ended: Emitted when a segment finishes playing (segment_id: int)
        subtitle_changed: Emitted when subtitle needs updating (time: float)
    """
    
    # Signals
    position_changed = Signal(float)  # position in seconds
    playback_started = Signal()
    playback_stopped = Signal()
    segment_ended = Signal(int)       # segment_id
    # subtitle_changed = Signal(float)  # time in seconds
    media_duration_changed = Signal(float)  # duration in seconds
    

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # Media components
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        
        # State
        self.state = PlaybackState()
        self.media_path: Optional[str] = None
        self.media_duration: float = 0.0  # in seconds
        self.media_metadata: dict = {}
        
        # Connect internal signals
        self.player.positionChanged.connect(self._onPositionChanged)
        self.player.playbackStateChanged.connect(self._onPlaybackStateChanged)
        self.player.durationChanged.connect(self._onDurationChanged)
        
        self.log.debug("MediaPlayerController initialized")
    

    def loadMedia(self, filepath: str) -> bool:
        """
        Load a media file for playback.
        
        Args:
            filepath: Path to the media file
            
        Returns:
            True if loading initiated successfully, False otherwise
        """
        if not filepath:
            self.log.warning("Attempted to load media with empty filepath")
            return False
        
        self.log.info(f"Loading media file: {filepath}")
        self.stop()
        self.state.reset()
        
        self.media_path = filepath
        self.player.setSource(QUrl.fromLocalFile(filepath))

        # Load metadata
        self.media_metadata = cache.get_media_metadata(filepath)
        return True


    def unloadMedia(self) -> None:
        """Unload current media and reset state"""
        self.log.debug("Unloading media")
        self.stop()
        self.player.setSource(QUrl())
        self.media_path = None
        self.media_duration = 0.0
        self.state.reset()
    

    def getMediaMetadata(self) -> dict:
        """Get metadata of the currently loaded media"""
        return self.media_metadata  


    def play(self) -> bool:
        """
        Start or resume playback.
        
        Returns:
            True if playback started, False otherwise
        """
        if not self.hasMedia():
            self.log.warning("Cannot play: no media loaded")
            return False
        
        self.player.play()
        self.log.debug(f"Playback started at {self.state.current_position:.3f}s")
        return True
    

    def pause(self) -> None:
        """Pause playback"""
        if self.isPlaying():
            self.player.pause()
            self.log.debug(f"Playback paused at {self.state.current_position:.3f}s")
    

    def stop(self) -> None:
        """Stop playback and reset to beginning"""
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.stop()
            self.log.debug("Playback stopped")
    

    def togglePlayPause(self) -> bool:
        """
        Toggle between play and pause.
        
        Returns:
            True if now playing, False if now paused
        """
        if self.isPlaying():
            self.pause()
            return False
        else:
            self.play()
            return True
    
    
    def playSegment(self, segment: Segment, segment_id: SegmentId = -1) -> bool:
        """
        Play a specific segment. Leave segment_id to -1 to play the selection.
        
        Args:
            segment: Tuple of (start, end) in seconds
            segment_id: Optional segment identifier
            
        Returns:
            True if playback started, False otherwise
        """
        log.debug(f"playSegment({segment=}, {segment_id=})")
        if not self.hasMedia():
            self.log.warning("Cannot play segment: no media loaded")
            return False
        
        start, end = segment
        
        if start < 0.0 or end > self.media_duration:
            self.log.warning(f"Segment out of bounds: [{start}, {end}]")
            return False
        
        if start >= end:
            self.log.warning(f"Invalid segment: start >= end [{start}, {end}]")
            return False
        
        self.state.playing_segment_id = segment_id
        self.seekTo(start)
        self.play()
        return True
    

    def playSelection(self, selection: Segment) -> bool:
        """
        Play a selection (without a segment ID).
        
        Args:
            selection: Tuple of (start, end) in seconds
            
        Returns:
            True if playback started, False otherwise
        """
        self.state.playing_segment_id = -1
        return self.playSegment(selection)
    

    def deselectSegment(self) -> None:
        self.state.playing_segment_id = -1


    def seekTo(self, position_sec: float) -> None:
        """
        Seek to a specific position.
        
        Args:
            position_sec: Position in seconds
        """
        if not self.hasMedia():
            self.log.warning("Cannot seek: no media loaded")
            return
        
        position_sec = max(0.0, min(position_sec, self.media_duration))
        position_ms = int(position_sec * 1000)
        self.player.setPosition(position_ms)
        self.state.current_position = position_sec
        self.log.debug(f"Seeked to {position_sec:.3f}s")
    

    def seekRelative(self, delta_sec: float) -> None:
        """
        Seek relative to current position.
        
        Args:
            delta_sec: Number of seconds to skip (positive or negative)
        """
        new_position = self.state.current_position + delta_sec
        self.seekTo(new_position)
    

    def getCurrentPosition(self) -> float:
        """Get current playback position in seconds"""
        return self.state.current_position
    

    def setVolume(self, volume: float) -> None:
        """
        Set audio volume.
        
        Args:
            volume: Volume level from 0.0 to 1.0
        """
        volume = max(0.0, min(1.0, volume))
        self.audio_output.setVolume(volume)
    

    def getVolume(self) -> float:
        """Get current volume level (0.0 to 1.0)"""
        return self.audio_output.volume()
    

    def setPlaybackRate(self, rate: float) -> None:
        """
        Set playback speed.
        
        Args:
            rate: Playback rate (1.0 = normal, 0.5 = half speed, 2.0 = double speed)
        """
        rate = max(0.1, min(4.0, rate))  # Reasonable bounds
        self.player.setPlaybackRate(rate)
        self.log.debug(f"Playback rate set to {rate:.2f}x")
    

    def getPlaybackRate(self) -> float:
        """Get current playback rate"""
        return self.player.playbackRate()
    

    def setLooping(self, enabled: bool) -> None:
        """
        Enable or disable looping.
        
        Args:
            enabled: True to enable looping, False to disable
        """
        self.state.looping = enabled
        self.log.debug(f"Looping {'enabled' if enabled else 'disabled'}")
    

    def isLooping(self) -> bool:
        """Check if looping is enabled"""
        return self.state.looping
    

    def toggleLooping(self) -> bool:
        """
        Toggle looping state.
        
        Returns:
            New looping state
        """
        self.state.looping = not self.state.looping
        return self.state.looping
    

    def isPlaying(self) -> bool:
        """Check if media is currently playing"""
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    

    def isPaused(self) -> bool:
        """Check if media is paused"""
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    

    def isStopped(self) -> bool:
        """Check if media is stopped"""
        return self.player.playbackState() == QMediaPlayer.PlaybackState.StoppedState
    

    def hasMedia(self) -> bool:
        """Check if media is loaded"""
        return self.media_path is not None and not self.player.source().isEmpty()
    

    def getPlayingSegmentId(self) -> int:
        """
        Get the ID of the currently playing segment.
        
        Returns:
            Segment ID, or -1 if not playing a segment
        """
        return self.state.playing_segment_id
    

    def getDuration(self) -> float:
        """Get total media duration in seconds"""
        return self.media_duration
    

    def connectVideoWidget(self, video_widget) -> None:
        """
        Connect a video widget to the media player.
        
        Args:
            video_widget: Video widget instance
        """
        try:
            video_widget.connectToMediaPlayer(self.player)
            self.log.debug("Video widget connected")
        except Exception as e:
            self.log.error(f"Failed to connect video widget: {e}")
    

    @Slot(int)
    def _onPositionChanged(self, position_ms: int) -> None:
        """Handle position changes from the media player"""
        position_sec = position_ms / 1000.0
        self.state.current_position = position_sec
        
        # Emit position update
        self.position_changed.emit(position_sec)
        
        # Emit subtitle update
        # self.subtitle_changed.emit(position_sec)
    

    def _onPlaybackStateChanged(self, state: QMediaPlayer.PlaybackState) -> None:
        """Handle playback state changes"""
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.state.is_playing = True
            self.playback_started.emit()
        elif state in (QMediaPlayer.PlaybackState.PausedState, QMediaPlayer.PlaybackState.StoppedState):
            self.state.is_playing = False
            self.playback_stopped.emit()
    

    def _onDurationChanged(self, duration_ms: int) -> None:
        """Handle media duration changes"""
        self.media_duration = duration_ms / 1000.0
        self.log.info(f"Media duration: {self.media_duration:.2f}s")
        self.media_duration_changed.emit(self.media_duration)
    
    
    def cleanup(self) -> None:
        """Clean up resources before destruction"""
        self.log.debug("Cleaning up MediaPlayerController")
        self.stop()
        self.unloadMedia()