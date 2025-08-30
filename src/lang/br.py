"""
Breton
"""

from ostilhou.asr.models import _get_model_list
from ostilhou.asr.post_processing import post_process_text as ostilhou_post_process_text
from ostilhou.text import (
    pre_process,
    sentence_stats, normalize_sentence,
    tokenize, detokenize, TokenType
)



NAME = "brezhoneg"
SHORT_NAME = "br"


def get_model_dictionary() -> dict:
    """
    Returns:
        A dictionary of models, where each key is the model name
        and each value is a dictionary of the form:
            {'name':str, 'type':str, 'description':str, 'url':str}
    """
    model_list = _get_model_list()
    models = dict()
    for model in model_list:
        models[model['name']] = model
    return models


def get_hunspell_url() -> str:
    return (
        "https://github.com/Drouizig/hunspell-br/raw/refs/heads/master/br_FR.dic"
        "https://github.com/Drouizig/hunspell-br/raw/refs/heads/master/br_FR.aff",
    )


def post_process_text(text: str, normalize:bool=False) -> str:
    return ostilhou_post_process_text(text, normalize=normalize)


def pre_process_density(text: str) -> str:
    return text


def process_word_for_alignment(s: str) -> str:
    """
    Process sentence for alignment matching used for 'smart splitting'
    Special tokens and metadata are already accounted for.
    Character '^' is reserved and used to signal a special token
    """
    s = pre_process(s)
    if sentence_stats(s)["decimal"] > 0:
        s = normalize_sentence(s, autocorrect=True)
    s = s.replace("c'h", 'X')
    s = s.replace('ch', 'S')
    s = s.replace('à', 'a')
    s = s.replace('â', 'a')
    s = s.replace('ù', 'u')
    s = s.replace('û', 'u')
    s = s.replace('ê', 'e')
    s = s.replace('é', 'e')
    s = s.replace('è', 'e')
    # Remove silent letters
    s = s.replace('h', '')
    # Remove double-letters
    chars = []
    for c in s:
        if not chars:
            chars.append(c)
        elif c != chars[-1]:
            chars.append(c)
    s = ''.join(chars)
    return s


def remove_fillers(text: str) -> str:
    return detokenize(tokenize(text), filter_out={TokenType.FILLER})