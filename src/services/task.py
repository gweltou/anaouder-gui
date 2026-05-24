
import subprocess

from PySide6.QtCore import QThread, QObject, Signal

from src.services.logger import logger



class TaskWorker(QThread):
    progress_pc = Signal(int)      # 0–100
    completed = Signal()
    failed = Signal()
    stopped = Signal()


    def __init__(self, parent=None):
        super().__init__(parent)

        self.description = "Worker thread"
        self._must_stop = False
        self._process = None    # Optional subprocess


    def stop(self):
        self._must_stop = True

        # Force process to stop
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        

    def run(self):
        raise NotImplementedError



class TaskQueue(QObject):
    """Runs a list of TaskWorkers sequentially, one at a time."""

    all_completed = Signal()
    all_stopped = Signal()
    any_failed = Signal()
    task_started = Signal(int, int, str)   # current index, total count
    progress_pc = Signal(int)      # 0–100


    def __init__(self, tasks: list[TaskWorker], parent=None):
        super().__init__(parent)
        self._tasks = tasks
        self._current = 0
        self._stopped = False


    def start(self):
        self._current = 0
        self._stopped = False
        self._run_next()


    def stop(self):
        self._stopped = True
        task = self._current_task()
        if task and task.isRunning():
            task.stop()


    def _current_task(self) -> TaskWorker | None:
        if self._current < len(self._tasks):
            return self._tasks[self._current]
        return None


    def _run_next(self):
        task = self._current_task()
        if task is None:
            self.all_completed.emit()
            return

        self.task_started.emit(self._current, len(self._tasks), task.description)
        self.progress_pc.emit(0)   # reset bar

        task.progress_pc.connect(self.progress_pc)
        task.completed.connect(self._on_task_completed)
        task.stopped.connect(self._on_task_stopped)
        task.failed.connect(self._on_task_failed)

        logger.debug(f"Starting task {task}", self.__class__.__name__)
        task.start()


    def _on_task_completed(self):
        self.progress_pc.emit(100)
        self._current += 1
        if self._stopped:
            self.all_stopped.emit()
        else:
            self._run_next()


    def _on_task_stopped(self):
        self.all_stopped.emit()


    def _on_task_failed(self):
        self.any_failed.emit()