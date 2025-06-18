import re
import jiwer

from src.lang import prepWordForAlignment
from src.utils import PUNCTUATION


SPLIT_TOKEN = '|'


def smart_split(text, position, vosk_tokens):
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
    # print(text)
    # print(' '.join([t[2] for t in vosk_tokens]))

    left_text = text[:position].rstrip()
    right_text = text[position:].lstrip()

    result = align_texts_with_vosk_tokens(' '.join([left_text, SPLIT_TOKEN, right_text]), vosk_tokens)
    print(' '.join([left_text, SPLIT_TOKEN, right_text]))
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


def prep_word(word: str) -> str:
    return prepWordForAlignment(word)  # Language dependent pre-processing


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
    text = text.lower()
    text = text.replace('\n', ' ')
    text = re.sub(r"{.+?}", '', text)        # Ignore metadata
    text = re.sub(r"<[A-Z\']+?>", '¤', text) # Replace special tokens
    text = text.replace('*', '')
    text = text.replace('-', ' ')            # Needed for Breton, but how does it impact other languages ?
    text = text.replace('.', ' ')
    text = filter_out_chars(text, PUNCTUATION + "'")

    # Create matrix
    gt_words = [prep_word(w) for w in text.split()]
    gt_words = list(filter(lambda x: x, gt_words))

    hyp_words = [ (prep_word(t[2]), t[0], t[1]) for t in vosk_tokens]

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