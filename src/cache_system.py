from typing import List, Dict, Optional
import os
import hashlib
import json
from datetime import datetime
from pathlib import Path
import numpy as np
import copy

from src.utils import get_cache_directory



def calculate_fingerprint(filepath: str):
    """
    Calculate a unique fingerprint to use as
    identifiers for the cache system
    To make it fast, it only calculates a checksum on
    different parts of the file rather than the whole file

    Arugment:
        filepath (str)
            A path to a audio file
    
    Returns:
        A unique fingerprint for any given file
    """

    file_size = os.stat(filepath).st_size
    block_size = 4096
    n_blocks = min(8, int(file_size / block_size))
    loc_step = file_size // n_blocks
    
    sha256_hash = hashlib.sha256()
    with open(filepath, 'rb') as _f:
        loc = 0
        for i in range(n_blocks):
            if loc + block_size > file_size:
                sha256_hash.update(file_size - (loc + block_size))
                break
            _f.seek(loc)
            sha256_hash.update(_f.read(block_size))
            loc += loc_step

    return sha256_hash.hexdigest()



class CacheSystem:
    def __init__(self):
        # Copy of cache found on disk
        self.media_cache : Dict[str, Dict] = dict()
        self.doc_cache : Dict[str, Dict] = dict()

        # Volatile cache of last accessed media metadatas (scenes and transcription)
        self.media_metadata_cache : Dict[str, Dict] = dict()

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
    

    def _get_transcription_path(self, fingerprint: str) -> Path:
        return self.transcriptions_dir / f"{fingerprint}.tsv"

    def _get_waveform_path(self, fingerprint: str) -> Path:
        return self.waveforms_dir / f"{fingerprint}.npy"

    def _get_scenes_path(self, fingerprint: str) -> Path:
        return self.scenes_dir / f"{fingerprint}.tsv"

    
    def _load_root_cache(self):
        # Media file cache, indexed by audio fingerprint
        print("Loading media cache")
        try:
            with open(self.media_cache_path, 'r') as _f:
                for jsonl in _f:
                    entry : dict = json.loads(jsonl)
                    if "last_access" not in entry:
                        entry["last_access"] = datetime.now().timestamp()
                    fingerprint = entry.pop("fingerprint")
                    if "waveform_size" not in entry:
                        waveform_path = self._get_waveform_path(fingerprint)
                        if waveform_path.exists():
                            # Add "waveform_size" property if absent
                            entry.update(
                                { "waveform_size": waveform_path.stat().st_size }
                            )
                            self._media_cache_dirty = True
                    self.media_cache[fingerprint] = entry
        except (FileNotFoundError, json.JSONDecodeError):
            self.media_cache = dict()
        
        # Document cache, indexed by document path
        print("Loading document cache")
        try:
            with open(self.doc_cache_path, 'r') as _f:
                for jsonl in _f:
                    entry = json.loads(jsonl)
                    if "last_access" not in entry:
                        entry["last_access"] = datetime.now().timestamp()
                    doc_path = entry.pop("file_path")
                    self.doc_cache[doc_path] = entry
        except (FileNotFoundError, json.JSONDecodeError):
            # We should try to restore the database
            self.doc_cache = dict()


    def _save_root_cache_to_disk(self):
        """Save cache root files to disk in line json format (jsonl)"""
        if self._media_cache_dirty:
            try:
                with open(self.media_cache_path, 'w') as _f:
                    for fg in sorted(
                            self.media_cache,
                            key=lambda e: self.media_cache[e]["last_access"],
                            reverse=True
                        ):
                        entry = self.media_cache[fg]
                        entry["fingerprint"] = fg
                        json.dump(entry, _f)
                        _f.write('\n')
                self._media_cache_dirty = False
            except Exception as e:
                print(f"Error: Couln't save media cache to disk ({e})")
        
        if self._doc_cache_dirty:
            try:
                with open(self.doc_cache_path, 'w') as _f:
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
                print(f"Error: Couln't save document cache to disk ({e})")


    def get_media_metadata(self, filepath: str):
        """
        Get cached metadata (except waveform) for media file and update access time
        The waveform is never present in returned dictionary
        You must call the 'get_waveform' method instead
        """
        fingerprint = calculate_fingerprint(filepath)

        if fingerprint in self.media_cache:
            metadata = self.media_cache[fingerprint]
            metadata["last_access"] = datetime.now().timestamp()

            transcription = self._get_transcription_from_disk(fingerprint)
            if transcription == None:
                # No transcription exists on disk
                transcription = []
                metadata["transcription_completed"] = False
                metadata["transcription_progress"] = 0.0
            scenes = self._get_scenes_from_disk(fingerprint)

            # Update media cache on disk
            self._media_cache_dirty = True
            self._save_root_cache_to_disk()

            # We keep a copy of the loaded transcription and scenes in cache
            self.media_metadata_cache[fingerprint] = {
                "transcription": transcription,
                "scenes": scenes
            }

            all_metadata = copy.deepcopy(metadata)
            all_metadata["transcription"] = transcription[:]
            all_metadata["scenes"] = scenes[:]
            return all_metadata
        return {}


    def update_media_metadata(self, audio_path: str, metadata: dict):
        """Save media metadatas on disk"""
        print(f"Update media metadata cache, {audio_path}")
        fingerprint = calculate_fingerprint(audio_path)

        metadata = copy.deepcopy(metadata)

        metadata["file_path"] = os.path.abspath(audio_path) # Not sure we need this one, but hey...
        metadata["last_access"] = datetime.now().timestamp()
        
        if "waveform" in metadata:
            # Save waveform to disk
            # the "waveform" property is present only if it was created or updated
            waveform_path = self._get_waveform_path(fingerprint)
            np.save(waveform_path, metadata.pop("waveform"))
            metadata.update(
                { "waveform_size": os.stat(waveform_path).st_size }
            )
        
        if transcription := metadata.pop("transcription", []):
            # Check if provided transcription differs from previously loaded one
            if fingerprint in self.media_metadata_cache:
                cached_transcription = self.media_metadata_cache[fingerprint]["transcription"]
                if not cached_transcription or transcription != cached_transcription:
                    self._save_transcription_to_disk(fingerprint, transcription)
                    self.media_metadata_cache[fingerprint]["transcription"] = transcription
            else:
                self._save_transcription_to_disk(fingerprint, transcription)
        
        if scenes := metadata.pop("scenes", []):
            # Check if provided transcription differs from previously loaded one
            if fingerprint in self.media_metadata_cache:
                cached_scenes = self.media_metadata_cache[fingerprint].get("scenes", [])
                if not cached_scenes or scenes != cached_scenes:
                    self._save_scenes_to_disk(fingerprint, scenes)
                    self.media_metadata_cache[fingerprint]["scenes"] = scenes
            else:
                self._save_scenes_to_disk(fingerprint, scenes)
        
        if fingerprint not in self.media_cache:
            self.media_cache[fingerprint] = {"file_size": os.stat(audio_path).st_size}
        self.media_cache[fingerprint].update(metadata)

        self._media_cache_dirty = True
        self._save_root_cache_to_disk()
    

    def _access_doc(self, filepath: str):
        """Get cached metadata for document file and update access time"""
        if filepath in self.doc_cache:
            metadata = self.doc_cache[filepath]
            metadata["last_access"] = datetime.now().timestamp()
            self._doc_cache_dirty = True
            self._save_root_cache_to_disk()
            return metadata
        return {}


    def get_doc_metadata(self, filepath: str):
        filepath = os.path.abspath(filepath)
        if filepath in self.doc_cache:
            return self._access_doc(filepath)
        return {}
    

    def update_doc_metadata(self, filepath: str, metadata: dict):
        filepath = os.path.abspath(filepath)
        metadata["last_access"] = datetime.now().timestamp()
        self.doc_cache.update({filepath: metadata})

        self._doc_cache_dirty = True
        self._save_root_cache_to_disk()
    

    def _get_scenes_from_disk(self, fingerprint: str) -> List[tuple]:
        """Return the cached scenes transitions for this media file"""
        filepath = self._get_scenes_path(fingerprint)
        if not os.path.exists(filepath):
            return []
        try:
            scenes = []
            with open(filepath, 'r') as _f:
                for line in _f.readlines():
                    t, r, g, b = line.strip().split('\t')
                    scenes.append((float(t), int(r), int(g), int(b)))
            return scenes
        except Exception as e:
            print(f"Error reading scenes file: {e}")
            return []


    def _save_scenes_to_disk(self, fingerprint: str, scenes: List[tuple]):
        """
        Scenes format:
            Each scene is on a different line.
            On each line, fields are separated by a tab (\t).
            Fields: onset time, red channel, green channel, blue channel
        """
        
        # Write scenes to disk
        print("Writting scenes to disk")
        with open(self._get_scenes_path(fingerprint), 'w') as _fout:
            for scene in scenes:
                scene = [ str(f) for f in scene ]
                _fout.write('\t'.join(scene) + '\n')
        self._media_cache_dirty = True


    def _get_transcription_from_disk(self, fingerprint: str) -> Optional[List[tuple]]:
        """
        Return the cached transcription for this media file.
        Return None if no transcription exists on disk
        """
        filepath = self._get_transcription_path(fingerprint)
        if not os.path.exists(filepath):
            return None
        try:
            tokens = []
            with open(filepath, 'r') as _f:
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


    def _save_transcription_to_disk(self, fingerprint: str, tokens: List[tuple]):
        """
        Transcription format:
            Each word is on a different line.
            On each line, fields are separated by a tab (\t).
            Fields: word, start time, end time, confidence
        """
        
        # Write transcription to disk
        print("Writting transcription to disk")
        with open(self._get_transcription_path(fingerprint), 'w') as _fout:
            for tok in tokens:
                tok = [ str(t) for t in tok ]
                _fout.write('\t'.join(tok) + '\n')
        self._media_cache_dirty = True
    
    
    # def clear_transcription(self, audio_path: str) -> None:
    #     fp = calculate_fingerprint(audio_path)
    #     filepath = self._get_transcription_path(fp)
    #     if os.path.exists(filepath):
    #         os.remove(filepath)


    def get_waveform(self, audio_path: str) -> Optional[np.ndarray]:
        print("Loading waveform from cache")
        fingerprint = calculate_fingerprint(audio_path)
        if fingerprint in self.media_cache:
            waveform_path = self._get_waveform_path(fingerprint)
            if os.path.exists(waveform_path):
                return np.load(waveform_path)
            else:
                print(f"Warning: file {waveform_path} doesn't exist.")
                return None
        return None
    

    def clear(self, audio_path: str) -> None:
        self.clear_transcription(audio_path)
        fingerprint = calculate_fingerprint(audio_path)
        del self.media_cache[fingerprint]
        self._save_root_cache_to_disk()