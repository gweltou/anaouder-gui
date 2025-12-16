"""
Anaouder - Automatic transcription and subtitling for the Breton language
Copyright (C) 2025  Gweltaz Duval-Guennoc (gweltou@hotmail.com)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""


from PySide6.QtCore import QRunnable, QThreadPool, Signal, QObject, QThread

from ostilhou.hspell import hs_dic_path


_hs = None



def get_hunspell_spylls_br():    
    global _hs
    if _hs != None:
        return _hs
    
    print("Loading Hunspell dictionary...")
    from spylls.hunspell import Dictionary as SpyllsDictionary

    _hs = SpyllsDictionary.from_files(hs_dic_path)
    return _hs



class HunspellSignals(QObject):
    finished = Signal(object)
    message = Signal(str)   # Sends a message to be displayed in the status bar


class HunspellLoader(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = HunspellSignals()
    
    def run(self):
        QThread.currentThread().setPriority(QThread.Priority.LowPriority)

        self.signals.message.emit(QObject.tr("Loading hunspell dictionary") + "...")
        hunspell = get_hunspell_spylls_br()

        self.signals.finished.emit(hunspell)
        self.signals.message.emit(QObject.tr("Hunspell dictionary loaded"))


def toggleMisspelling(self, checked):
    self.show_misspelling = checked
    
    if checked:
        loader = HunspellLoader()
        loader.signals.finished.connect(self._on_hunspell_loaded)
        QThreadPool.globalInstance().start(loader)
    else:
        self.hunspell = None
        self.rehighlight()


def _on_hunspell_loaded(self, hunspell):
    self.hunspell = hunspell
    if self.show_misspelling:
        self.rehighlight()