"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

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


from typing import List, Dict, Optional
from functools import lru_cache
import logging
import os
import hashlib
import copy
import json
from datetime import datetime
from pathlib import Path
import numpy as np

from src.utils import get_cache_directory


type Fingerprint = str


log = logging.getLogger(__name__)



@lru_cache  # Memoization
def calculate_fingerprint(file_path: Path) -> Fingerprint:
    """
    Calculate a unique fingerprint to use as identifiers
    for the cache system.
    To make it fast, it only calculates a checksum on
    different parts of the file rather than the whole file.

    Args:
        filepath (Path)
            A path to a audio file
    
    Returns:
        A unique fingerprint for any given file
    """

    file_size = file_path.stat().st_size
    block_size = 4096
    n_blocks = min(8, int(file_size / block_size))
    loc_step = file_size // n_blocks
    
    sha256_hash = hashlib.sha256()
    with file_path.open('rb') as _f:
        loc = 0
        for i in range(n_blocks):
            if loc + block_size > file_size:
                _f.seek(loc)
                sha256_hash.update(_f.read(file_size - loc))
                break
            _f.seek(loc)
            sha256_hash.update(_f.read(block_size))
            loc += loc_step

    return sha256_hash.hexdigest()



class CacheSystem:
    """
    The cache consists of different parts:

    Two jsonl file, which serve as databases for:

    * Media cache (accessed with fingerprint)
        file_path
        file_size
        duration
        waveform_size
        transcription_progress
        transcription_completed
        last_access
        fingerprint
    
    * Document cache (accessed by file path)
        cursor_pos
        waveform_pos
        waveform_pps
        show_scenes
        show_margin
        video_open
        show_misspelling
        last_access
    
    Folders for:
        * scenes (.tsv)
        * transcriptions (.tsv)
        * waveforms (numpy arrays .npy)
    """

    def __init__(self) -> None:
        # Copy in memory of cache loaded from disk
        self.media_cache: Dict[Fingerprint, Dict] = dict()
        self.doc_cache: Dict[str, Dict] = dict()

        # Volatile cache of last accessed media metadatas (scenes and transcription)
        self.scenes_cache: Dict[Fingerprint, List[tuple]] = dict()
        self.transcriptions_cache: Dict[Fingerprint, List[tuple]] = dict()

        self._media_cache_dirty = False # True when the db has unsaved changes
        self._doc_cache_dirty = False

        cache_dir = get_cache_directory()
        
        self.transcriptions_dir = cache_dir / "transcriptions"
        self.waveforms_dir = cache_dir / "waveforms"
        self.scenes_dir = cache_dir / "scenes"

        for d in (self.transcriptions_dir, self.waveforms_dir, self.scenes_dir):
            if not d.exists():
                os.makedirs(d, exist_ok=True)
        
        self.media_cache_path = cache_dir / "media_cache.jsonl"
        self.doc_cache_path = cache_dir / "doc_cache.jsonl"

        self._load_root_cache()
    

    def _get_transcription_path(self, fingerprint: Fingerprint) -> Path:
        return self.transcriptions_dir / f"{fingerprint}.tsv"

    def _get_waveform_path(self, fingerprint: Fingerprint) -> Path:
        return self.waveforms_dir / f"{fingerprint}.npy"

    def _get_scenes_path(self, fingerprint: Fingerprint) -> Path:
        return self.scenes_dir / f"{fingerprint}.tsv"


    def _load_root_cache(self) -> None:
        # Media file cache, indexed by audio fingerprint
        log.info("Loading media cache")
        try:
            with self.media_cache_path.open('r') as _jsonl_file:
                for line in _jsonl_file:
                    entry: dict = json.loads(line)

                    # Add the "last_access" property, if not present
                    if "last_access" not in entry:
                        entry["last_access"] = datetime.now().timestamp()

                    fingerprint = entry["fingerprint"]

                    # Add the "waveform_size" property, if not present
                    if "waveform_size" not in entry:
                        waveform_path = self._get_waveform_path(fingerprint)
                        if waveform_path.exists():
                            entry.update(
                                { "waveform_size": waveform_path.stat().st_size }
                            )
                            self._media_cache_dirty = True
                    self.media_cache[fingerprint] = entry

        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.error(f"Could not open media cache file: {e}")
            self.media_cache = dict()
        
        # Document cache, indexed by document path
        log.info("Loading document cache")
        try:
            with self.doc_cache_path.open('r') as _jsonl_file:
                for line in _jsonl_file:
                    entry = json.loads(line)

                    # Add the "last_access" property, if not present
                    if "last_access" not in entry:
                        entry["last_access"] = datetime.now().timestamp()

                    doc_path = entry.pop("file_path")
                    self.doc_cache[doc_path] = entry
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.error(f"Could not open media cache file: {e}")
            # We should try to restore the database
            self.doc_cache = dict()


    def _save_root_cache_to_disk(self) -> None:
        """ Save cache root files to disk in jsonl format """
        if self._media_cache_dirty:
            try:
                with self.media_cache_path.open('w') as _f:
                    for fg in sorted(
                            self.media_cache,
                            key=lambda fg: self.media_cache[fg]["last_access"],
                            reverse=True
                        ):
                        entry = self.media_cache[fg]
                        entry["fingerprint"] = fg
                        json.dump(entry, _f)
                        _f.write('\n')
                self._media_cache_dirty = False
            except Exception as e:
                log.error(f"Error: Couln't save media cache to disk ({e})")
        
        if self._doc_cache_dirty:
            try:
                with self.doc_cache_path.open('w') as _f:
                    for key in sorted(
                            self.doc_cache,
                            key=lambda e: self.doc_cache[e]["last_access"],
                            reverse=True
                        ):
                        entry = self.doc_cache[key]
                        entry["file_path"] = key
                        json.dump(entry, _f)
                        _f.write('\n')
                self._doc_cache_dirty = False
            except Exception as e:
                log.error(f"Error: Couln't save document cache to disk ({e})")


    def get_media_metadata(self, media_path: Path) -> dict:
        """
        Get cached metadata (except waveform) for media file and update access time
        The waveform is never present in returned dictionary
        You must call the 'get_waveform' method instead
        """
        fingerprint = calculate_fingerprint(media_path)

        if fingerprint in self.media_cache:
            metadata = self.media_cache[fingerprint]
            metadata["last_access"] = datetime.now().timestamp()

            # Update media cache on disk
            self._media_cache_dirty = True
            # self._save_root_cache_to_disk()

            return metadata
        
        return {}


    def update_media_metadata(self, media_path: Path, metadata: dict = {}) -> None:
        """Save media metadatas on disk"""
        log.info(f"Update media metadata cache for {media_path}")
        fingerprint = calculate_fingerprint(media_path)

        metadata["file_path"] = str(media_path.absolute())
        metadata["last_access"] = datetime.now().timestamp()

        if fingerprint not in self.media_cache:
            self.media_cache[fingerprint] = {"file_size": media_path.stat().st_size}
        
        self.media_cache[fingerprint].update(metadata)

        self._media_cache_dirty = True
        self._save_root_cache_to_disk()


    def get_doc_metadata(self, file_path: Path) -> dict:
        """ Get cached metadata for document file and update access time """

        file_path = file_path.absolute()
        if file_path in self.doc_cache:
            metadata = self.doc_cache[str(file_path)]
            metadata["last_access"] = datetime.now().timestamp()
            self._doc_cache_dirty = True
            self._save_root_cache_to_disk()
            return metadata
        
        return {}


    def update_doc_metadata(self, file_path: Path, metadata: dict) -> None:
        file_path = file_path.absolute()
        metadata["last_access"] = datetime.now().timestamp()
        self.doc_cache.update({str(file_path): metadata})

        self._doc_cache_dirty = True
        self._save_root_cache_to_disk()


    def get_media_transcription(self, file_path: Path) -> Optional[List[tuple]]:
        fingerprint = calculate_fingerprint(file_path)

        if fingerprint not in self.transcriptions_cache:        
            transcription = self._get_transcription_from_disk(fingerprint)
            if transcription is None:
                return None
            
            self.transcriptions_cache[fingerprint] = transcription

        return self.transcriptions_cache[fingerprint]


    def _get_transcription_from_disk(self, fingerprint: Fingerprint) -> Optional[List[tuple]]:
        """
        Return the cached transcription for this media file.
        Return None if no transcription exists on disk
        """
        file_path = self._get_transcription_path(fingerprint)
        # if not os.path.exists(filepath):
        if not file_path.exists():
            return None
        
        try:
            tokens = []
            with file_path.open('r') as _f:
                for line in _f.readlines():
                    fields = line.strip().split('\t')
                    token = (
                        float(fields[0]),   # Start
                        float(fields[1]),   # End
                        fields[2],          # Word
                        float(fields[3]),   # Conf
                        fields[4],          # Lang
                    )
                    tokens.append(token)
            return tokens
        except Exception as e:
            print(f"Error reading transcription file: {e}")
            return None
    

    def set_media_transcription(self, media_path: Path, tokens: list):
        """
        Transcription format:
            Each word/token is on a different line.
            On each line, fields are separated by a tab (\t).
            Fields: word, start time, end time, confidence
        """

        log.debug(f"update_media_transcription, {tokens=}")
        fingerprint = calculate_fingerprint(media_path)

        self.transcriptions_cache[fingerprint] = tokens

        # Write on disk
        with open(self._get_transcription_path(fingerprint), 'w') as _fout:
            for tok in tokens:
                tok = [ str(t) for t in tok ]
                _fout.write('\t'.join(tok) + '\n')

        self.update_media_metadata(media_path)
 

    def append_media_transcription(self, media_path: Path, tokens: list):
        log.debug(f"append_media_transcription {media_path=} {tokens=}")
        fingerprint = calculate_fingerprint(media_path)

        self.transcriptions_cache[fingerprint].extend(tokens)

        # Write on disk, append mode
        with self._get_transcription_path(fingerprint).open('a') as _fout:
            for tok in tokens:
                tok = [ str(t) for t in tok ]
                _fout.write('\t'.join(tok) + '\n')
        
        self.update_media_metadata(media_path)


    def get_media_scenes(self, media_path: Path) -> Optional[List[tuple]]:
        fingerprint = calculate_fingerprint(media_path)

        if fingerprint in self.scenes_cache:        
            return self.scenes_cache[fingerprint]

        return self._get_scenes_from_disk(fingerprint)


    def _get_scenes_from_disk(self, fingerprint: Fingerprint) -> List[tuple]:
        """Return the cached scenes transitions for this media file"""
        file_path = self._get_scenes_path(fingerprint)
        if not file_path.exists():
            return []
        try:
            scenes = []
            with file_path.open('r') as _f:
                for line in _f.readlines():
                    t, r, g, b = line.strip().split('\t')
                    scenes.append((float(t), int(r), int(g), int(b)))
            return scenes
        except Exception as e:
            print(f"Error reading scenes file: {e}")
            return []


    def _save_scenes_to_disk(self, fingerprint: Fingerprint, scenes: List[tuple]) -> None:
        """
        Scenes format:
            Each scene is on a different line.
            On each line, fields are separated by a tab (\t).
            Fields: onset time, red channel, green channel, blue channel
        """
        
        # Write scenes to disk
        log.info("Writting scenes to disk")
        with self._get_scenes_path(fingerprint).open('w') as _fout:
            for scene in scenes:
                scene = [ str(f) for f in scene ]
                _fout.write('\t'.join(scene) + '\n')
        self._media_cache_dirty = True

    
    def get_waveform(self, media_path: Path) -> Optional[np.ndarray]:
        log.info("Loading waveform from cache")
        fingerprint = calculate_fingerprint(media_path)

        if fingerprint in self.media_cache:
            waveform_path = self._get_waveform_path(fingerprint)
            if os.path.exists(waveform_path):
                return np.load(waveform_path)
            else:
                log.info(f"File {waveform_path} doesn't exist.")
        return None
    

    def set_waveform(self, media_path: Path, audio_samples: np.ndarray):
        fingerprint = calculate_fingerprint(media_path)

        # Save waveform to disk
        waveform_path = self._get_waveform_path(fingerprint)
        log.info(f"Saving the waveform to {waveform_path}")
        np.save(waveform_path, audio_samples)

        self.update_media_metadata(media_path, { "waveform_size": waveform_path.stat().st_size })

    
    # def clear_transcription(self, audio_path: str) -> None:
    #     fp = calculate_fingerprint(audio_path)
    #     filepath = self._get_transcription_path(fp)
    #     if os.path.exists(filepath):
    #         os.remove(filepath)

    # def clear(self, audio_path: str) -> None:
    #     self.clear_transcription(audio_path)
    #     fingerprint = calculate_fingerprint(audio_path)
    #     del self.media_cache[fingerprint]
    #     self._save_root_cache_to_disk()



# Global cache system instance
cache = CacheSystem()