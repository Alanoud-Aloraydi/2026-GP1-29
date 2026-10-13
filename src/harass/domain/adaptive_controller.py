"""Beta-Bernoulli Thompson selection, following Shukla et al. (2026), Algorithm 4."""

# Algorithm source: https://arxiv.org/html/2606.26936v1#A5.SS1.SSS3 .

import random
from dataclasses import dataclass


@dataclass
class _Posterior:
    successes: int = 1
    failures: int = 1


class ThompsonController:
    """Update run-local arm posteriors from known verdicts, separated by context."""

    def __init__(self, random_seed: int) -> None:
        """Start with uniform Beta(1, 1) priors and a private random stream."""
        self._random = random.Random(random_seed)
        self._posteriors: dict[tuple[str, str], _Posterior] = {}

    def choose(self, context: str, arms: tuple[str, ...]) -> str:
        """Draw from each eligible posterior and return its highest sample."""
        if not arms:
            raise ValueError("At least one eligible arm is required.")
        samples = {}
        for arm in sorted(set(arms)):
            posterior = self._posteriors.setdefault((context, arm), _Posterior())
            samples[arm] = self._random.betavariate(posterior.successes, posterior.failures)
        return max(samples, key=lambda arm: samples[arm])

    def observe(self, context: str, arm: str, defect: bool | None) -> None:
        """Update only the selected arm when the observation is known."""
        if defect is None:
            return
        posterior = self._posteriors.setdefault((context, arm), _Posterior())
        if defect:
            posterior.successes += 1
        else:
            posterior.failures += 1

    def posterior(self, context: str, arm: str) -> tuple[int, int]:
        """Return the auditable Beta parameters before or after an observation."""
        posterior = self._posteriors.get((context, arm), _Posterior())
        return posterior.successes, posterior.failures

    def snapshot(self) -> dict[str, object]:
        """Export RNG and posterior state without executable serialization."""
        return {
            "random_state": self._random.getstate(),
            "posteriors": [
                [context, arm, posterior.successes, posterior.failures]
                for (context, arm), posterior in sorted(self._posteriors.items())
            ],
        }

    def restore(self, state: dict[str, object]) -> None:
        """Restore a previously exported JSON-compatible controller state."""
        random_state = state["random_state"]
        if not isinstance(random_state, (list, tuple)) or len(random_state) != 3:
            raise ValueError("Invalid controller random state.")
        values = random_state[1]
        if not isinstance(values, (list, tuple)):
            raise ValueError("Invalid controller random state values.")
        self._random.setstate((random_state[0], tuple(values), random_state[2]))
        posteriors = state["posteriors"]
        if not isinstance(posteriors, (list, tuple)):
            raise ValueError("Invalid controller posteriors.")
        restored = {}
        for row in posteriors:
            if not isinstance(row, (list, tuple)) or len(row) != 4:
                raise ValueError("Invalid controller posterior entry.")
            successes, failures = int(row[2]), int(row[3])
            if successes < 1 or failures < 1:
                raise ValueError("Controller posteriors must remain positive.")
            restored[str(row[0]), str(row[1])] = _Posterior(successes, failures)
        self._posteriors = restored
