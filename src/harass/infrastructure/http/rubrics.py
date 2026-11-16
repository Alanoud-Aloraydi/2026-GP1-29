"""The rubric wording that every decision-model judge shows its model."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

RUBRIC_DIRECTORY = Path(__file__).parent / "rubrics"
FINGERPRINT_LENGTH = 12


def rubric_fingerprint() -> str:
    """Identify the rubric files so a report names the prompt version."""
    digest = hashlib.sha256()
    for path in sorted(RUBRIC_DIRECTORY.glob("*.yaml")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:FINGERPRINT_LENGTH]


@dataclass(frozen=True)
class Rubrics:
    """The category definitions and attack wording shown to a judge model."""

    categories: dict[str, str]
    attack_true: str
    attack_false: str


def load_rubrics(directory: Path) -> Rubrics:
    """Read the rubric files that the chat judges are built from."""
    classifier = yaml.safe_load(
        (directory / "response_categories.yaml").read_text(encoding="utf-8")
    )
    question = yaml.safe_load(
        (directory / "attack_success_question.yaml").read_text(
            encoding="utf-8"
        )
    )
    return Rubrics(
        categories={
            item["name"]: " ".join(item["description"].split())
            for item in classifier["categories"]
        },
        attack_true=" ".join(question["true_description"].split()),
        attack_false=" ".join(question["false_description"].split()),
    )
