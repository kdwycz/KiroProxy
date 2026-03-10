# Kiro API Proxy
try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("kiroproxy")
except Exception:
    __version__ = "1.8.0"
