from typing import List, Dict, Optional
import os
import hashlib
import json
from datetime import datetime
from pathlib import Path
import numpy as np

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
        self.media_cache : Dict[str, Dict] = dict()
        self.doc_cache : Dict[str, Dict] = dict()

        self._media_cache_dirty = False # True when the db has unsaved changes
        self._doc_cache_dirty = False

        cache_dir = get_cache_directory()
        
        self.transcriptions_dir = cache_dir / "transcripts"
        if not self.transcriptions_dir.exists():
            os.makedirs(self.transcriptions_dir, exist_ok=True)
        
        self.waveforms_dir = cache_dir / "waveforms"
        if not self.waveforms_dir.exists():
            os.makedirs(self.waveforms_dir, exist_ok=True)
        
        self.media_cache_path = cache_dir / "media_cache.jsonl"
        self.doc_cache_path = cache_dir / "doc_cache.jsonl"

        self.load()
        
    
    def load(self):
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
                        if os.path.exists(waveform_path):
                            # Add "waveform_size" property if absent
                            entry.update(
                                { "waveform_size": os.stat(waveform_path).st_size }
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

    

    def _get_transcription_path(self, fingerprint: str) -> str:
        return self.transcriptions_dir / f"{fingerprint}.tsv"

    def _get_waveform_path(self, fingerprint: str) -> str:
        return self.waveforms_dir / f"{fingerprint}.npy"


    def save(self):
        """Save cache to disk in line json format (jsonl)"""
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
    

    def _access_media(self, fingerprint: int) -> dict:
        """Get cached metadata for media file and update access time"""
        if fingerprint in self.media_cache:
            metadata = self.media_cache[fingerprint]
            metadata["last_access"] = datetime.now().timestamp()
            self._media_cache_dirty = True
            self.save()
            return metadata
        return {}


    def get_media_metadata(self, file_path: str):
        fingerprint = calculate_fingerprint(file_path)
        return self._access_media(fingerprint)


    def update_media_metadata(self, audio_path: str, metadata: dict):
        print(f"Update media metadata cache, {audio_path}, {metadata}")
        fingerprint = calculate_fingerprint(audio_path)

        metadata["file_path"] = os.path.abspath(audio_path) # Not sure we need this one, but hey...
        metadata["last_access"] = datetime.now().timestamp()
        
        if "waveform" in metadata:
            # Save waveform to disk
            waveform_path = self._get_waveform_path(fingerprint)
            np.save(waveform_path, metadata.pop("waveform"))
            metadata.update(
                { "waveform_size": os.stat(waveform_path).st_size }
            )
        
        if fingerprint not in self.media_cache:
            self.media_cache[fingerprint] = {"file_size": os.stat(audio_path).st_size}
        
        cached_metadata = self.media_cache[fingerprint]
        cached_metadata.update(metadata)

        self._media_cache_dirty = True
        self.save()
    

    def _access_doc(self, file_path: str):
        """Get cached metadata for document file and update access time"""
        if file_path in self.doc_cache:
            metadata = self.doc_cache[file_path]
            metadata["last_access"] = datetime.now().timestamp()
            self._doc_cache_dirty = True
            self.save()
            return metadata
        return {}


    def get_doc_metadata(self, file_path: str):
        file_path = os.path.abspath(file_path)
        if file_path in self.doc_cache:
            return self._access_doc(file_path)
        return {}
    

    def update_doc_metadata(self, file_path: str, metadata: dict):
        file_path = os.path.abspath(file_path)
        metadata["last_access"] = datetime.now().timestamp()
        self.doc_cache.update({file_path: metadata})

        self._doc_cache_dirty = True
        self.save()
    

    def get_transcription(self, audio_path: str) -> List[dict]:
        """Return the cached transcription for this audio file"""
        fp = calculate_fingerprint(audio_path)
        self._access_media(fp)
        filepath = self._get_transcription_path(fp)
        if not os.path.exists(filepath):
            return []
        tokens = []
        with open(filepath, 'r') as _f:
            for line in _f.readlines():
                fields = line.strip().split('\t')
                token = {
                    "word": fields[0],
                    "start": float(fields[1]),
                    "end": float(fields[2]),
                    "conf": float(fields[3]),
                }
                if len(fields) > 4:
                    token["lang"] = fields[4]
                tokens.append(token)
        return tokens


    def update_transcription(self, audio_path: str, tokens: List[dict], lang='br'):
        """
        Transcription format:
            Each word is on a different line.
            On each line, fields are separated by a tab (\t).
            Fields: word, start time, end time, confidence
        """
        old_tokens = self.get_transcription(audio_path)
        
        # Update old transcription with new tokens
        updated_tokens = []
        segment_start = tokens[0]["start"]
        segment_end = tokens[-1]["end"]
        idx = 0
        for tok in old_tokens:
            if tok["end"] > segment_start:
                break
            updated_tokens.append(tok)
            idx += 1
        for tok in tokens:
            tok["lang"] = lang
            updated_tokens.append(tok)
        while idx < len(old_tokens) and old_tokens[idx]["start"] < segment_end:
            idx += 1
        for tok in old_tokens[idx:]:
            updated_tokens.append(tok)
        
        # Write transcription to disk
        fp = calculate_fingerprint(audio_path)
        with open(self._get_transcription_path(fp), 'w') as _fout:
            for tok in updated_tokens:
                fields = [ tok["word"], str(tok["start"]), str(tok["end"]), str(tok["conf"]) ]
                if "lang" in tok:
                    fields.append(tok["lang"])
                _fout.write('\t'.join(fields) + '\n')
        self._media_cache_dirty = True
    
    
    def clear_transcritpion(self, audio_path: str) -> None:
        fp = calculate_fingerprint(audio_path)
        filepath = self._get_transcription_path(fp)
        if os.path.exists(filepath):
            os.remove(filepath)


    def get_waveform(self, audio_path: str) -> Optional[np.ndarray]:
        print("get waveform cache")
        fp = calculate_fingerprint(audio_path)
        if fp in self.media_cache:
            self._access_media(fp) # Update access time
            waveform_path = self._get_waveform_path(fp)
            if os.path.exists(waveform_path):
                return np.load(waveform_path)
            else:
                print(f"Warning: file {waveform_path} doesn't exist.")
                return None
        return None
    

    def clear(self, audio_path: str) -> None:
        self.clear_transcritpion(audio_path)
        fingerprint = calculate_fingerprint(audio_path)
        del self.media_cache[fingerprint]
        self.save()