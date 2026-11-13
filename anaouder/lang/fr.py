"""
Français
"""


NAME = "français"
SHORT_NAME = "fr"


def get_model_dictionary() -> dict:
    """
    Returns:
        A dictionary of models, where each key is the model name
        and each value is a dictionary of the form:
            {'type':str, 'description':str, 'url':str}
    """
    models = {
        "vosk-model-small-fr-0.22": {
            "short-name": "vosk-small-fr-0.22",
            "type": "vosk",
            "description-fr": "",
            "url": "https://alphacephei.com/vosk/models/vosk-model-small-fr-0.22.zip",
            "sha256": "cabf6180e177eb9b3a9a9d43a437bd5e549f3a7d09525e5d69a3fed787be12ad"
        }
    }
    
    return models


def get_hunspell_url() -> str:
    return (
        "https://github.com/Drouizig/hunspell-br/raw/refs/heads/master/br_FR.dic"
        "https://github.com/Drouizig/hunspell-br/raw/refs/heads/master/br_FR.aff",
    )


def post_process_text(text: str, normalize:bool=False) -> str:
    return text


def pre_process_density(text: str) -> str:
    return text
