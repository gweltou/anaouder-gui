"""
Cymraeg
"""

NAME = "cymraeg"
SHORT_NAME = "cy"


def get_model_dictionary() -> dict:
    """
    Returns:
        A dictionary of models, where keys are model names
        and each value is a dictionary of the form:
            {'type':str, 'description':str, 'url':str}
    """
    models = {
        "kaldi-cy": {
            "type": "vosk",
            "description-en": "",
            "url": "https://huggingface.co/techiaith/kaldi-cy/resolve/main/model_cy.tar.gz",
            "md5": "f2a568e18c6e77b336db5b5e8e22c1b5"
        }
    }
    return models


def get_hunspell_url() -> str:
    return (
        "https://github.com/techiaith/hunspell-cy-llafar/raw/refs/heads/main/cy_GB_llafar.dic"
        "https://github.com/techiaith/hunspell-cy-llafar/raw/refs/heads/main/cy_GB.aff",
    )


def post_process_text(text: str) -> str:
    return text


def pre_process_density(text: str) -> str:
    return text
