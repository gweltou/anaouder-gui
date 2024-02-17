#! /usr/bin/env python3
# -*- coding: utf-8 -*-


from typing import Tuple, List, Dict

import re



def read_file_drop_comments(path: str) -> List[str]:
    lines = []
    with open(path, 'r') as f:
        for l in f.readlines():
            l = l.strip()
            if l and not l.startswith('#'):
                lines.append(l)
    return lines




Segment = Tuple[int, int]

def load_segments_data(segfile: str) -> List[Segment]:
    """ Load audio segments delimiters from a `.seg` file
        Return a list of segments
    """

    segments = []
    with open(segfile, 'r') as f:
        for l in f.readlines():
            l = l.strip()
            if not l or l.startswith('#'):
                continue
            t = l.split()
            start = int(t[0])
            stop = int(t[1])
            segments.append((start, stop))
    
    return segments



def load_text_data(filename) -> List[Tuple[str, Dict]]:
    """ 
        Return list of sentences with metadata.
        Metadata dictionaries will always have, at least, the "speaker" and "gender" keys.

        Return
        ------
            list of tuple (text sentences, metadata)
    """
    utterances = []
    current_speaker = 'unknown'
    current_gender = 'unknown'
    no_lm = False
    for l in read_file_drop_comments(filename):
        # Extract speaker id and other metadata
        l, metadata = extract_metadata(l)
        if "speaker" in metadata:
            current_speaker = metadata["speaker"]
        else:
            metadata["speaker"] = current_speaker
        
        if "gender" in metadata:
            current_gender = metadata["gender"]
        else:
            metadata["gender"] = current_gender
        
        if "parser" in metadata:
            if "no-lm" in metadata["parser"]: no_lm = True
            elif "add-lm" in metadata["parser"]: no_lm = False
        else:
            if no_lm:
                metadata["parser"] = ["no-lm"]
        if l:
            utterances.append((l, metadata))
    return utterances



##############################  METADATA  ##############################

METADATA_PATTERN = re.compile(r'{\s*(.+?)\s*}')
METADATA_UNIT_PATTERN = re.compile(r"\s*([\w\s:,_'/.-]+)\s*")
SPEAKER_NAME_PATTERN = re.compile(r"(?:spk\s*:\s*)?([\w '_-]+?)")
SPEAKER_ID_PATTERN_DEPR = re.compile(r'([-\'\w]+):*([mf])*')
KEYVAL_PATTERN = re.compile(r"([\w_'-]+)\s*:\s*([\w ,_'.:/-]+?)\s*")

_VALID_PARAMS = {
    "source", "source-audio",
    "tags",
    "parser",
    "author", "authors",
    "licence",
    "speaker", "spk",
    "gender",
    "accent",
    "modifications",
    "transcription"
#    "phon",
}


def extract_metadata(sentence: str) -> Tuple[str, dict]:
    """ Returns the sentence stripped of its metadata (if any)
        and a dictionary of metadata
        Keeps unknown word marker '{?}'
    """
    metadata = dict()

    match = METADATA_PATTERN.search(sentence)
    while match:
        start, end = match.span()
        if match.group(1) == '?':       # Unknown words {?}
            if "unknown" not in metadata: metadata["unknown"] = []
            sub = sentence[:end]
            metadata["unknown"].append(len(sub.split())-1)
        else:
            for unit in METADATA_UNIT_PATTERN.finditer(match.group(1)):
                speaker_name = SPEAKER_NAME_PATTERN.fullmatch(unit.group(1))
                if speaker_name:
                    metadata["speaker"] = speaker_name.group(1).replace(' ', '_').lower()
                    continue
                
                key_val = KEYVAL_PATTERN.fullmatch(unit.group(1))
                if key_val:
                    key, val = key_val.group(1), key_val.group(2)

                    if key in _VALID_PARAMS:
                        if key in ("tags", "author", "accent"):
                            val = [v.strip().replace(' ', '_') for v in val.split(',') if v.strip()]
                        metadata[key_val.group(1)] = val

                    else:
                        speaker_name_depr = SPEAKER_ID_PATTERN_DEPR.fullmatch(unit.group(1))
                        if speaker_name_depr:
                            metadata["speaker"] = speaker_name_depr.group(1)
                            if speaker_name_depr.group(2) in 'fm':
                                metadata["gender"] = speaker_name_depr.group(2)
                            continue    
                        else:
                            print(Fore.RED + f"Wrong metadata: {unit.group(0)}" + Fore.RESET)

        sentence = sentence[:start] + sentence[end:]
        match = METADATA_PATTERN.search(sentence)
    
    return sentence.strip(), metadata
