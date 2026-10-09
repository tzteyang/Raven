"""Read a stage prompt together with the shared expression standard in prompts/voice.md."""

from pathlib import Path

PROMPTS = Path(__file__).resolve().parent / "prompts"


def prompt(name: str) -> str:
    return f"{(PROMPTS / name).read_text().strip()}\n\n{(PROMPTS / 'voice.md').read_text().strip()}"
