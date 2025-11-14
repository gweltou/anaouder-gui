import re
import jiwer
from math import inf

from src.lang import prepTextForAlignment
from src.utils import PUNCTUATION


SPLIT_TOKEN = '|'



class SmartSplitError(Exception):
    """Custom exception for errors during smart splitting
    """
    pass



def smart_split_text(text: str, position: int, vosk_tokens: list) -> tuple:
    """
    Split a text at a given character position
    while trying to keep it aligned with timecoded tokens
    
    Args:
        text: text to be splitted
        position: character position where to split
        vosk_tokens: list of timecoded tokens of the format
            (start_time, end_time, word, confidence, language)

    Returns:
        A 2-tuple consisting of the left part and the right part,
        where each part is a list of timecoded tokens
    """

    if not can_smart_split(text, vosk_tokens):
        # Will call prepare_sentence, like align_text_with_vosk_token
        # We could take advantage of that to avoid redundant calls
        raise SmartSplitError("CER is too high")

    left_text = text[:position].rstrip()
    right_text = text[position:].lstrip()

    result = align_texts_with_vosk_tokens(' '.join([left_text, SPLIT_TOKEN, right_text]), vosk_tokens)
    
    # Find index of split token
    i = 0
    for t, _ in result:
        if t == SPLIT_TOKEN:
            break
        i += 1
    
    if i == 0:
        return [], [vosk_tokens[0][0], vosk_tokens[-1][1]]
    if i == len(result) - 1:
        return [vosk_tokens[0][0], vosk_tokens[-1][1]], []

    # Check if neighbours are valid
    prev_token = None
    r = 1
    while i-r >= 0:
        if result[i-r][1] == None:
            r += 1
        else:
            prev_token = result[i-r][1]
            break
    if prev_token == None:
        prev_token = (vosk_tokens[0][2], vosk_tokens[0][0], vosk_tokens[0][1])
    
    next_token = None
    r = 1
    while i+r < len(result):
        if result[i+r][1] == None:
            r += 1
        else:
            next_token = result[i+r][1]
            break
    if next_token == None:
        next_token = (vosk_tokens[-1][2], vosk_tokens[-1][0], vosk_tokens[-1][1])
    
    left_seg = [vosk_tokens[0][0], prev_token[2]]
    right_seg = [next_token[1], vosk_tokens[-1][1]]
    return left_seg, right_seg


def smart_split_time(text: str, timepos: float, vosk_tokens: list) -> tuple:
    """
    Split a text based on a gap index from a hypotheses token list
    
    Args:
        text: text to be splitted
        idx: gap index between two tokens
        vosk_tokens: list of timecoded tokens of the format
            (start_time, end_time, word, confidence, language)

    Returns:
        A 2-tuple consisting of the left text and the right text
    """
    if not can_smart_split(text, vosk_tokens):
        # Will call prepare_sentence.
        # We could take advantage of that to avoid redundant calls
        raise SmartSplitError("CER is too high")

    # Find the best location to split the transcribed sentence
    idx = 0
    for t_start, t_end, word, _, _ in vosk_tokens:
        if timepos < t_start + (t_end - t_start) * 0.5:
            break
        idx += 1

    # Add a split token in the list of transcribed tokens
    left_tokens = vosk_tokens[:idx]
    right_tokens = vosk_tokens[idx:]
    left_hyp = ' '.join([ t[2] for t in left_tokens ])
    right_hyp = ' '.join([ t[2] for t in right_tokens ])

    words = text.split()

    # Iterate to find the best sentence split candidate
    best_idx, best_score = -1, inf
    for i in range(len(words) + 1):
        left_split = prep_sentence(' '.join(words[:i]))
        right_split = prep_sentence(' '.join(words[i:]))
        score = (
            0.5 * jiwer.cer(left_hyp, left_split)
            + 0.5 * jiwer.cer(right_hyp, right_split)
        )
        if score < best_score:
            best_idx = i
            best_score = score

    return (' '.join(words[:best_idx]), ' '.join(words[best_idx:]))


def can_smart_split(text: str, vosk_tokens: list):
    # Simplify text representation
    gt = prep_sentence(text)
    hyp = prep_sentence(' '.join([t[2] for t in vosk_tokens]))
    cer = jiwer.cer(gt, hyp)
    print(f"{cer=}")
    return cer < 0.5


def prep_sentence(sentence: str, remove_spaces=True) -> str:
    """
    Return a simplified representation of the given sentence,
    for more better alignment
    """
    sentence = sentence.lower()
    sentence = sentence.replace('\n', ' ')
    sentence = re.sub(r"{.+?}", '', sentence)        # Ignore metadata
    sentence = re.sub(r"<[A-Z\']+?>", '¤', sentence) # Replace special tokens
    sentence = sentence.replace('*', '')
    sentence = sentence.replace('-', ' ')            # Needed for Breton, but how does it impact other languages?
    sentence = sentence.replace('.', ' ')
    sentence = filter_out_chars(sentence, PUNCTUATION)

    normalized = prepTextForAlignment(sentence)

    if remove_spaces:
        sentence = normalized.replace(' ', '')
        
    return sentence


def align_texts_with_vosk_tokens(text: str, vosk_tokens: list) -> list:
    """
    Args:
        text: ground truth text
        vosk_tokens: list of tuples, where each tuple represents a single token
            with the format (start_time, end_time, word, confidence, language)
    
    Returns:
        list of tuple, where each tuple represent an alignment candidate
            with the format (ground_truth_word, (hyp_word, start, end))
    """
    # Simplify text representation
    gt_words = prep_sentence(text, remove_spaces=False).split()

    hyp_words = [ (prepTextForAlignment(t[2]), t[0], t[1]) for t in vosk_tokens]

    n, m = len(gt_words), len(hyp_words)
    dp = [[float('inf')] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0

    del_cost = 1.0
    ins_cost = 1.0
    
    # Fill the matrix using Levenshtein distance
    for i in range(n + 1):
        for j in range(m + 1):
            if i > 0 and j > 0:
                if gt_words[i-1] == hyp_words[j-1][0]:
                    cost = 0 
                else:
                    cost = jiwer.cer(gt_words[i-1], hyp_words[j-1][0])
                dp[i][j] = min(dp[i][j], dp[i-1][j-1] + cost)
            if i > 0:
                dp[i][j] = min(dp[i][j], dp[i-1][j] + del_cost)  # deletion
            if j > 0:
                dp[i][j] = min(dp[i][j], dp[i][j-1] + ins_cost)  # insertion
    # _print_matrix(dp)
    
    # Backtrack to find alignment
    alignment = []
    i, j = n, m
    while i > 0 or j > 0:
        sub_cost = jiwer.cer(gt_words[i-1], hyp_words[j-1][0])
        if (i > 0 and j > 0 and dp[i][j] == dp[i-1][j-1] + sub_cost):
            alignment.append((gt_words[i-1], hyp_words[j-1]))
            i, j = i-1, j-1
        elif i > 0 and dp[i][j] == dp[i-1][j] + del_cost:
            alignment.append((gt_words[i-1], None))
            i -= 1
        else:
            alignment.append((None, hyp_words[j-1]))
            j -= 1
    
    return list(reversed(alignment))


def _print_matrix(matrix):
    # 2D matrix
    for row in matrix:
        r = [ f"{val:.2f}" for val in row ]
        print(f"[{' '.join(r)}]")


def filter_out_chars(text: str, chars: str) -> str:
    """Remove given characters from a string"""

    filtered_text = ""
    for l in text:
        if not l in chars: filtered_text += l
    return filtered_text