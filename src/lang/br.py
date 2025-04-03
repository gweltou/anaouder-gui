"""
Breton
"""

from ostilhou.asr.models import _get_model_list
from ostilhou.asr.post_processing import post_process_text as ostilhou_post_process_text


NAME = "brezhoneg"
SHORT_NAME = "br"


def get_model_dictionary() -> dict:
    """
    Returns:
        A dictionary of models, where each key is the model name
        and each value is a dictionary of the form:
            {'type':str, 'description':str, 'url':str}
    """
    model_list = _get_model_list()
    models = dict()
    for model in model_list:
        models[model['name']] = model
    return models


def post_process_text(text: str) -> str:
    return ostilhou_post_process_text(text)


def pre_process_density(text: str) -> str:
    return text