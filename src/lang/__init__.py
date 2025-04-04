from typing import List, Callable
from dataclasses import dataclass
import os
from importlib import import_module
import pkgutil
import shutil

from ostilhou.asr.models import _is_valid_vosk_model

from src.utils import _get_cache_directory


LANG_MODULES = ['br', 'cy']



@dataclass
class Language:
    name:                   str
    short_name:             str
    get_model_dict:         Callable[[], List[dict]]
    post_process_text:      Callable[[str], str] | None = None
    pre_process_density:    Callable[[str], str] | None = None

    def __post_init__(self):
        self.model_dir = _get_cache_directory(os.path.join("models", self.short_name))
        self.model_dict = self.get_model_dict()

    def load(self):
        pass
    
    def postProcessText(self, text: str) -> str:
        return self.post_process_text(text)

    def preProcessDensity(self, text: str) -> str:
        return self.pre_process_density(text)
    
    def getCachedModelList(self) -> List[str]:
        """Return a list of cached models"""
        model_dirs = [subdir.name for subdir in self.model_dir.iterdir() if _is_valid_vosk_model(subdir)]
        return sorted(model_dirs, reverse=True)

    def getDownloadableModelList(self) -> List[str]:
        """
        Return a list of models available for download
        without the models already downloaded
        """
        all_models = [ model for model in self.model_dict ]
        online_models = set(all_models).difference(set(getCachedModelList()))
        return sorted(online_models, reverse=True)

    def getModelList(self) -> List[str]:
        return sorted(self.get_model_dict().keys(), reverse=True)

    def deleteModel(self, model_name):
        if model_name in self.getCachedModelList():
            shutil.rmtree((self.model_dir / model_name).as_posix())


_languages = {}
_current_language : Language = None


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


def getModelCachePath(subdir: str = None) -> str:
    return _current_language.model_dir


def getModelPath(model_name: str) -> str:
    """Return the path to a cached model"""
    if model_name in _current_language.getCachedModelList():
        return os.path.join(_current_language.model_dir, model_name)


def getModelUrl(model_name: str) -> str:
    if model_name in _current_language.model_dict:
        return _current_language.model_dict[model_name]["url"]


def postProcessText(text: str) -> str:
    return _current_language.postProcessText(text)


def getLanguages():
    return sorted(_languages.keys())


def getCurrentLanguage() -> str:
    return _current_language.short_name


def loadLanguage(lang: str) -> None:
    """
    Keep Hunspell dictionary in memory for all previously loaded languages
    """
    global _current_language

    if lang in _languages:
        _current_language = _languages[lang]
    
    print("Language switched to", lang)


def getCachedModelList() -> list:
    """Return the list of models available locally"""
    return _current_language.getCachedModelList()


def getDownloadableModelList() -> list:
    """Return the list of downloadable models"""
    return _current_language.getDownloadableModelList()


def deleteModel(model_name: str):
    _current_language.deleteModel(model_name)