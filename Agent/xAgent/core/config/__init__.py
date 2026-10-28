"""Core configuration loading."""
import configparser
import os


class Config:
    def __init__(self, path: str | None = None):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.cfg = configparser.ConfigParser()
        self.cfg.read(path or os.path.join(self.base_dir, "config.ini"), encoding="utf-8-sig")
        self.llm = self.cfg["LLM"]
        self.base_url = self.llm.get("base_url", "").rstrip("/")
        self.model = self.llm.get("model", "")
        self.api_key = self.llm.get("api_key", "")


def load_config(path: str | None = None):
    return Config(path)
