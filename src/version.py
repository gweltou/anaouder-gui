from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("anaouder-gui")
except PackageNotFoundError:
    __version__ = "unknown"
