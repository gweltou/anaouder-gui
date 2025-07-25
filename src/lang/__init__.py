from typing import List, Callable
from dataclasses import dataclass
import os
from importlib import import_module
import shutil
import hashlib

from ostilhou.asr.models import _is_valid_vosk_model

from src.utils import get_cache_directory


LANG_MODULES = ['br', 'cy', 'fr']



@dataclass
class Language:
    name:                   str
    short_name:             str
    get_model_dict:         Callable[[], List[dict]]
    post_process_text:      Callable[[str, bool], str] | None = None
    pre_process_density:    Callable[[str], str] | None = None
    prepare_for_alignment:  Callable[[str], str] | None = None

    def __post_init__(self):
        self.model_dir = get_cache_directory(os.path.join("models", self.short_name))
        self.model_dict = self.get_model_dict()

    def load(self):
        pass
    
    def postProcessText(self, text: str, normalize: bool) -> str:
        return self.post_process_text(text, normalize)

    def preProcessDensity(self, text: str) -> str:
        return self.pre_process_density(text)
    
    def processTextForAlignment(self, text: str) -> str:
        return self.prepare_for_alignment(self, text)
    
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
        _languages[lang] = Language(
            name = getattr(module, "NAME").lower(),
            short_name = getattr(module, "SHORT_NAME").lower(),
            get_model_dict = getattr(module, "get_model_dictionary"),
            post_process_text = getattr(module, "post_process_text", None),
            prepare_for_alignment = getattr(module, "process_word_for_alignment", None),
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


def postProcessText(text: str, normalize: bool) -> str:
    return _current_language.postProcessText(text, normalize)


def prepWordForAlignment(text: str) -> str:
    return _current_language.prepare_for_alignment(text)


def getLanguages(long_name=False) -> List[str]:
    if long_name:
        return sorted([l.name.capitalize() for l in _languages.values()])
    return sorted(_languages.keys())


def getCurrentLanguage(long_name=False) -> str:
    if long_name:
        return _current_language.name.capitalize()
    return _current_language.short_name


def loadLanguage(lang: str) -> None:
    """
    Keep Hunspell dictionary in memory for all previously loaded languages
    """
    global _current_language

    lang = lang.lower()
    if len(lang) > 2:
        # Long name
        for l in _languages.values():
            if lang == l.name:
                lang = l.short_name
                break

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


def getMd5Sum(model_name: str) -> str:
    if model_name in _current_language.model_dict:
        return _current_language.model_dict[model_name].get("md5", "")