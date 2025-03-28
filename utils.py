from typing import List

from PySide6.QtCore import QRegularExpression


DIALOG_CHAR = '–'
LINE_BREAK = '\u2028'



def getSentenceSplits(text: str) -> List[tuple]:
        sentence_splits = [(0, len(text))]  # Used so that spelling checker doesn't check metadata parts

        # Metadata  
        expression = QRegularExpression(r"{\s*(.+?)\s*}")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            sentence_splits = _cutSentence(
                sentence_splits,
                match.capturedStart(),
                match.capturedStart()+match.capturedLength()
            )
        
        # Special tokens
        expression = QRegularExpression(r"<[a-zA-Z \'\/]+>")
        matches = expression.globalMatch(text)
        while matches.hasNext():
            match = matches.next()
            sentence_splits = _cutSentence(
                sentence_splits, match.capturedStart(),
                match.capturedStart()+match.capturedLength()
            )
        return sentence_splits


def _cutSentence(segments: list, start: int, end: int) -> list:
        """Subdivide a list of segments further, given a pair of indices"""
        assert start < end
        splitted = []
        for seg_start, seg_end in segments:
            if start >= seg_start and end <= seg_end:
                # Split this segment
                if start > seg_start:
                    pre_segment = (seg_start, start)
                    splitted.append(pre_segment)
                if end < seg_end:
                    post_segment = (end, seg_end)
                    splitted.append(post_segment)
            else:
                splitted.append((seg_start, seg_end))
        return splitted


def splitForSubtitle(text: str, size: int):
    """
    Split a single subtitle from a string
    or return original string in a tuple


    Returns:
        tuple (str, str)
            First split and rest of string
        or
        tuple (str,)
            No split. Same as original string
    """

    # Slit at dialog character
    if text.count(DIALOG_CHAR) >= 2:
        idx = text.find(DIALOG_CHAR)    # Ignore first one
        idx = text.find(DIALOG_CHAR, idx+1)
        return (text[:idx], text[idx:])

    text_segs = getSentenceSplits(text)
    text_len = sum([e-s for s, e in text_segs])
    if text_len > size:
        
        # Split at first dot
        dot_i = -1
        dot_rel_i = -1
        l = 0
        for start, end in text_segs:
            t = text[start:end]
            i = t.find('.')
            if i >= 0 and t.find('...') != i:
                dot_i = i
                dot_rel_i = l + i
                break
            l += end-start
            if l > size:
                 break
        if text_len * 0.33 < dot_rel_i < text_len * 0.66:
             return (text[:dot_i+1], text[dot_i+1:])
    
    return (text,)