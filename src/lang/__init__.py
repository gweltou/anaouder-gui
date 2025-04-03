from typing import List, Callable
from dataclasses import dataclass
import os
from importlib import import_module
import pkgutil

from ostilhou.asr.models import _is_valid_vosk_model

from src.utils import _get_cache_directory


LANG_MODULES = ['br', 'cy']

from . import br


print(f"{__package__=}")

_languages = {}
_current_language = None #_languages["br"]


@dataclass
class Language:
    name:                   str
    short_name:             str
    get_model_dict:         Callable[[], List[dict]]
    post_process_text:      Callable[[str], str] | None = None
    pre_process_density:    Callable[[str], str] | None = None

    def __post_init__(self):
        pass

    def load(self):
        pass
    
    def postProcessText(self, text: str) -> str:
        return self.post_process_text(text)

    def preProcessDensity(self, text: str) -> str:
        return self.pre_process_density(text)
    
    def getCachedModelList(self) -> List[str]:
        """Return a list of cached models"""
        model_cache_dir = _get_cache_directory(os.path.join("models", self.short_name))
        model_dirs = [subdir.name for subdir in model_cache_dir.iterdir() if _is_valid_vosk_model(subdir)]
        return model_dirs

    def getModelList(self) -> List[str]:
        return sorted(self.get_model_dict().keys())


for lang in LANG_MODULES:
    module = import_module(f"{__package__}.{lang}")
    try:
        name = getattr(module, "NAME")
        short_name = getattr(module, "SHORT_NAME")
        get_model_dict = getattr(module, "get_model_dictionary")
        post_process_text = getattr(module, "post_process_text")
        _languages[lang] = Language(
            name=name,
            short_name=short_name,
            get_model_dict=get_model_dict,
            post_process_text=post_process_text
        )
    except:
        print("Wrong Language Type")

# print(_current_language.getCachedModelList())



# def _download(model_name: str, root: str) -> str:
#     """
#     Get the requested model path on disk or download it if not present
#     """
#     os.makedirs(root, exist_ok=True)
    
#     model_path = os.path.join(root, model_name)

#     for model in _model_list:
#         if model["name"] == model_name:
#             url = model["url"]
#             break
#     else:
#         raise RuntimeError("Couldn't find requested model url")
    
#     download_target = os.path.join(root, os.path.basename(url))

#     print(f"Downloading model from {url}", file=sys.stderr)
#     with urllib.request.urlopen(url, context=_certifi_context) as source, open(download_target, "wb") as output:
#         with tqdm(
#             total=int(source.info().get("Content-Length")),
#             ncols=80,
#             unit="iB",
#             unit_scale=True,
#             unit_divisor=1024,
#         ) as loop:
#             while True:
#                 buffer = source.read(8192)
#                 if not buffer:
#                     break

#                 output.write(buffer)
#                 loop.update(len(buffer))
    
#     with zipfile.ZipFile(download_target, 'r') as zip_ref:
#         zip_ref.extractall(root)

#     os.remove(download_target)

#     return model_path


def getModel(model_name: str):
    """
    Load a Vosk model from the current language
    If the model is not is not present locally, the model will be downloaded
    """
    pass
    

def postProcessText(text: str) -> str:
    return _current_language.postProcessText(text)



def getLanguages():
    return sorted(_languages.keys())


def loadLanguage(lang: str) -> None:
    """
    Keep Hunspell dictionary in memory for all previously loaded languages
    """
    global _current_language

    if lang in _languages:
        _current_language = _languages[lang]


def getCachedModelList() -> list:
    return _current_language.getCachedModelList()