"""
Cymraeg
"""

NAME = "cymraeg"
SHORT_NAME = "cy"


def get_model_dictionary() -> dict:
    """
    Returns:
        A dictionary of models, where each key is the model name
        and each value is a dictionary of the form:
            {'type':str, 'description':str, 'url':str}
    """
    models = dict()
    return models


def post_process_text(text: str) -> str:
    return text


def pre_process_density(text: str) -> str:
    return text