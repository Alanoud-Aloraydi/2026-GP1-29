"""Tests for the judge server script, run with stand-ins for the GPU stack."""

import contextlib
import importlib.util
import json
import math
import sys
import threading
import types
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import pytest

MIB = 1024 * 1024
SERVER_SCRIPT = Path(__file__).resolve().parents[3] / "tools" / "judge_host" / "judge_server.py"


class Model(Protocol):
    """The parts of a decision model that the tests use."""

    @property
    def loaded(self) -> bool:
        """Report whether the model occupies the GPU."""

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Answer one request."""

    def unload(self) -> None:
        """Release the GPU memory."""

    def release_if_idle(self) -> None:
        """Release the GPU memory when idle."""


class ServerScript(Protocol):
    """The parts of the script that the tests use."""

    IDLE_SECONDS: float
    MODELS: dict[str, Any]
    DecisionModel: Callable[[Any], Model]
    Handler: Any
    ThreadingHTTPServer: Any
    LoadedFaisal: Callable[..., Any]
    plain: Callable[[object], object]
    faisal_task: Callable[..., str]
    decide_faisal: Callable[..., dict[str, Any]]
    decide_qwenguard: Callable[..., dict[str, Any]]
    yes_probability: Callable[[list[tuple[str, float]]], float]
    gpu_memory: Callable[[], dict[str, int] | None]
    LoadedGuard: Callable[..., Any]


@dataclass
class Stack:
    """The loaded script and the counters of its stand-in GPU stack."""

    script: ServerScript
    loads: list[str]
    cache_clears: list[int]


class FakeTensor:
    """Stand in for a tensor that converts to a list."""

    def __init__(self, values: list[float]) -> None:
        """Keep the values."""
        self.values = values

    def tolist(self) -> list[float]:
        """Return the values as plain numbers."""
        return self.values

    def float(self) -> "FakeTensor":
        """Return the same values, as a float tensor would."""
        return self

    def __getitem__(self, selection: object) -> "FakeTensor":
        """Select the values at the given positions, or pass through."""
        if isinstance(selection, list):
            return FakeTensor([self.values[index] for index in selection])
        return self


class FakeModel:
    """Stand in for the loaded d1 model."""

    def system_one(self, state: str, questions: dict[str, Any]) -> dict[str, Any]:
        """Answer every question with the same choice."""
        return {
            "answers": {
                name: {"choice": "REF", "probabilities": FakeTensor([0.1, 0.9])}
                for name in questions
            },
            "usage": {"tokens": 5},
        }


@pytest.fixture
def stack(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Stack:
    """Load the script with the GPU libraries replaced by stand-ins."""
    loads: list[str] = []
    cache_clears: list[int] = []

    class AutoModel:
        """Count loads and return the fake model."""

        @staticmethod
        def from_pretrained(*args: object, **kwargs: object) -> object:
            """Pretend to load the model."""
            loads.append("load")
            return types.SimpleNamespace(to=lambda device: FakeModel())

    def softmax(scores: FakeTensor, dim: int) -> FakeTensor:
        """Turn scores into probabilities that sum to one."""
        total = sum(scores.values)
        return FakeTensor([value / total for value in scores.values])

    stand_ins: dict[str, dict[str, Any]] = {
        "torch": {
            "bfloat16": "bfloat16",
            "inference_mode": contextlib.nullcontext,
            "softmax": softmax,
            "cuda": types.SimpleNamespace(
                empty_cache=lambda: cache_clears.append(1),
                is_initialized=lambda: True,
                reset_peak_memory_stats=lambda: None,
                max_memory_allocated=lambda: 3072 * MIB,
                mem_get_info=lambda: (2048 * MIB, 8192 * MIB),
            ),
        },
        "transformers": {
            "AutoModel": AutoModel,
            "AutoModelForCausalLM": object,
            "AutoModelForImageTextToText": object,
            "AutoTokenizer": object,
            "BitsAndBytesConfig": object,
            "DynamicCache": list,
        },
        "huggingface_hub": {"snapshot_download": lambda *a, **k: None},
    }
    for name, attributes in stand_ins.items():
        module = types.ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location("judge_server", SERVER_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    return Stack(cast(ServerScript, script), loads, cache_clears)


def d1_model(stack: Stack) -> Model:
    """Build the decision model of the d1 specification."""
    return stack.script.DecisionModel(stack.script.MODELS["d1"])


D1_REQUEST = {"state": "s", "questions": {"category": {}}}


def test_the_model_loads_on_first_use_and_only_once(stack: Stack) -> None:
    """Starting the server costs no GPU memory until a request arrives."""
    model = d1_model(stack)

    assert not model.loaded
    model.decide(D1_REQUEST)
    model.decide(D1_REQUEST)

    assert model.loaded
    assert stack.loads == ["load"]


def test_unloading_frees_the_gpu_and_the_next_request_reloads(stack: Stack) -> None:
    """Another service can take the GPU between uses."""
    model = d1_model(stack)
    model.decide(D1_REQUEST)

    model.unload()

    assert not model.loaded
    assert stack.cache_clears == [1]
    model.decide(D1_REQUEST)
    assert stack.loads == ["load", "load"]


def test_an_idle_model_is_released_but_a_busy_one_is_kept(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only a model unused for longer than the idle limit is released."""
    model = d1_model(stack)
    model.decide(D1_REQUEST)

    model.release_if_idle()
    assert model.loaded

    monkeypatch.setattr(stack.script, "IDLE_SECONDS", -1)
    model.release_if_idle()
    assert not model.loaded


def test_answers_are_converted_to_plain_json(stack: Stack) -> None:
    """Tensors inside answers become lists."""
    answer = {"a": FakeTensor([0.25]), "b": (1, FakeTensor([2]))}

    assert stack.script.plain(answer) == {"a": [0.25], "b": [1, [2]]}


def test_loading_d1_switches_the_model_to_portable_attention(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The model must not call flash kernels that Windows PyTorch lacks."""
    attention = types.ModuleType("transformers_modules.d1.attention")
    attention._fused = lambda queries: True  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, attention.__name__, attention)

    d1_model(stack).decide(D1_REQUEST)

    assert attention._fused(object()) is False


def test_each_model_has_its_own_port(stack: Stack) -> None:
    """Both models can be served side by side."""
    ports = {name: spec.port for name, spec in stack.script.MODELS.items()}

    assert ports == {
        "d1": 8081,
        "faisal": 8082,
        "qwenguard": 8083,
        "qwenguard-small": 8084,
        "shieldstral": 8085,
    }


def test_the_yes_probability_renormalises_over_yes_and_no_only(stack: Stack) -> None:
    """Other tokens are ignored and spelling variants of an answer count."""
    probability = stack.script.yes_probability(
        [("The", -0.1), (" Yes", math.log(0.6)), ("no.", math.log(0.2))]
    )

    assert probability == pytest.approx(0.75)


def test_a_missing_answer_token_leaves_the_other_one_certain(stack: Stack) -> None:
    """Without a no among the best tokens, yes is the whole probability."""
    assert stack.script.yes_probability([("yes", -3.0)]) == 1.0
    assert stack.script.yes_probability([("no", -3.0)]) == 0.0


def test_an_answer_slot_without_yes_or_no_is_a_failure(stack: Stack) -> None:
    """The server refuses to invent a probability."""
    with pytest.raises(RuntimeError):
        stack.script.yes_probability([("maybe", -0.1)])


OPTIONS = [{"key": "yes", "description": "It does."}, {"key": "no", "description": "It does not."}]


def test_faisal_task_uses_the_trained_format(stack: Stack) -> None:
    """Options are lettered in order and keep their keys and descriptions."""
    task = json.loads(stack.script.faisal_task({"request": "r"}, "Which?", OPTIONS))

    assert task["state"] == {"request": "r"}
    assert task["question"] == "Which?"
    assert task["options"] == [
        {"label": "A", "key": "yes", "description": "It does."},
        {"label": "B", "key": "no", "description": "It does not."},
    ]


@pytest.mark.parametrize("count", [1, 25])
def test_faisal_rejects_a_bad_number_of_options(stack: Stack, count: int) -> None:
    """Faisal takes between two and twenty-four options."""
    options = [{"key": str(i), "description": "d"} for i in range(count)]

    with pytest.raises(ValueError):
        stack.script.faisal_task("s", "q", options)


def test_faisal_returns_one_probability_per_option(stack: Stack) -> None:
    """The scores of the option letters become a distribution by key."""

    class Logits:
        """Indexable logits that return a tensor for the last position."""

        def __getitem__(self, position: object) -> FakeTensor:
            return FakeTensor([1.0, 3.0] + [0.0] * 22)

    class Tokens:
        """Tokenizer output with a movable input ids field."""

        input_ids = types.SimpleNamespace(to=lambda device: "ids")

    class Tokenizer:
        """Tokenizer stand-in returning fixed tokens."""

        def apply_chat_template(self, *args: object, **kwargs: object) -> str:
            return "prompt"

        def __call__(self, *args: object, **kwargs: object) -> Tokens:
            return Tokens()

    class Network:
        """Network stand-in returning the fixed logits."""

        device = "cpu"

        def __call__(self, input_ids: object) -> object:
            return types.SimpleNamespace(logits=Logits())

    model = stack.script.LoadedFaisal(Network(), Tokenizer(), list(range(24)))

    answer = stack.script.decide_faisal(model, {"state": "s", "question": "q", "options": OPTIONS})

    assert set(answer["probabilities"]) == {"yes", "no"}
    assert answer["probabilities"]["no"] == pytest.approx(0.75)
    assert sum(answer["probabilities"].values()) == pytest.approx(1.0)


@pytest.fixture
def base_url(stack: Stack, tmp_path: Path) -> Iterator[str]:
    """Serve the handler on a free local port."""
    handler = stack.script.Handler
    handler.spec = stack.script.MODELS["d1"]
    handler.model = d1_model(stack)
    handler.log_file = tmp_path / "d1.log"
    http = stack.script.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{http.server_address[1]}"
    http.shutdown()
    http.server_close()


def post(url: str, payload: object) -> tuple[int, dict[str, Any]]:
    """Post JSON and return the status and decoded reply."""
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request) as reply:
            return reply.status, json.loads(reply.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def get(url: str) -> dict[str, Any]:
    """Fetch a JSON document."""
    with urllib.request.urlopen(url) as reply:
        document: dict[str, Any] = json.loads(reply.read())
    return document


def test_health_shows_whether_the_model_is_loaded(base_url: str) -> None:
    """The operator can tell if the GPU is occupied."""
    before = get(f"{base_url}/health")
    post(f"{base_url}/decide", D1_REQUEST)
    after = get(f"{base_url}/health")

    assert before["loaded"] is False
    assert after["loaded"] is True
    assert after["model"] == "LiquidAI/d1-2B"
    assert after["dtype"] == "bfloat16"
    assert after["gpu"] == {"free_mib": 2048, "total_mib": 8192}


def test_decide_answers_and_rejects_malformed_requests(base_url: str) -> None:
    """A valid request is answered; anything else is a bad request."""
    status, reply = post(f"{base_url}/decide", D1_REQUEST)
    assert status == 200
    assert reply["answers"]["category"]["probabilities"] == [0.1, 0.9]

    assert post(f"{base_url}/decide", {"state": 1})[0] == 400
    assert post(f"{base_url}/decide", [1, 2])[0] == 400
    assert post(f"{base_url}/missing", {})[0] == 404


def test_unload_endpoint_releases_the_model(base_url: str) -> None:
    """The operator can free the GPU remotely."""
    post(f"{base_url}/decide", D1_REQUEST)

    status, reply = post(f"{base_url}/unload", {})

    assert (status, reply) == (200, {"loaded": False})
    assert get(f"{base_url}/health")["loaded"] is False


def test_log_endpoint_returns_the_recent_lines(base_url: str, stack: Stack) -> None:
    """The operator can read the server log without touching the PC."""
    stack.script.Handler.log_file.write_text("first\nsecond\n", encoding="utf-8")

    assert get(f"{base_url}/log") == {"lines": ["first", "second"]}


class GuardTokenizer:
    """Tokenizer stand-in that records the conversation it is given."""

    def __init__(self) -> None:
        """Start without a recorded conversation."""
        self.conversations: list[list[dict[str, str]]] = []

    def apply_chat_template(self, messages: list[dict[str, str]], tokenize: bool) -> str:
        """Record the conversation and return a prompt."""
        self.conversations.append(messages)
        return "prompt"

    def __call__(self, texts: list[str], return_tensors: str) -> "GuardTokens":
        """Return fixed input tokens."""
        return GuardTokens()

    def decode(self, tokens: list[int], skip_special_tokens: bool) -> str:
        """Decode the new tokens into the verdict text."""
        return "Safety: Safe" + chr(10) + "Refusal: Yes" if tokens == [7, 8] else ""


class GuardIds:
    """Token ids that can be cut into columns like a one-row tensor."""

    def __init__(self, row: list[int]) -> None:
        """Keep the single row of ids."""
        self.row = row

    @property
    def shape(self) -> tuple[int, int]:
        """Return the batch size and the number of tokens."""
        return (1, len(self.row))

    def __getitem__(self, key: int | tuple[slice, slice]) -> "list[int] | GuardIds":
        """Return the row, or the columns between two positions."""
        if isinstance(key, int):
            return self.row
        return GuardIds(self.row[key[1]])


class GuardTokens:
    """Tokenizer output that moves to a device and exposes its ids."""

    input_ids = GuardIds([1, 2, 3])

    def to(self, device: object) -> "GuardTokens":
        """Stay in place, as there is only one device."""
        return self

    def keys(self) -> list[str]:
        """List the fields that become generation arguments."""
        return ["input_ids"]

    def __getitem__(self, key: str) -> GuardIds:
        """Return a field by name."""
        return self.input_ids


class GuardNetwork:
    """Network stand-in that records chunks and appends two verdict tokens."""

    device = "cpu"

    def __init__(self) -> None:
        """Start without any recorded prompt chunks."""
        self.chunks: list[list[int]] = []
        self.generation_cache: object = None
        self.model = self.read_chunk

    def read_chunk(self, input_ids: GuardIds, past_key_values: object, use_cache: bool) -> None:
        """Record one chunk of the prompt that was fed to the base network."""
        assert use_cache is True
        self.generation_cache = past_key_values
        self.chunks.append(input_ids.row)

    def generate(
        self, input_ids: GuardIds, past_key_values: object, max_new_tokens: int, do_sample: bool
    ) -> list[list[int]]:
        """Return the prompt followed by the verdict tokens."""
        assert do_sample is False
        assert past_key_values is self.generation_cache
        return [[*input_ids.row, 7, 8]]


def test_qwenguard_returns_the_decoded_verdict_text(stack: Stack) -> None:
    """The conversation is moderated greedily and only new tokens decoded."""
    tokenizer = GuardTokenizer()
    model = stack.script.LoadedGuard(GuardNetwork(), tokenizer)
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]

    answer = stack.script.decide_qwenguard(model, {"messages": messages})

    assert answer == {"text": "Safety: Safe" + chr(10) + "Refusal: Yes"}
    assert tokenizer.conversations == [messages]


@pytest.mark.parametrize(
    "messages", [[], [{"role": "system", "content": "x"}], [{"role": "user", "content": 3}]]
)
def test_qwenguard_rejects_malformed_conversations(
    stack: Stack, messages: list[dict[str, object]]
) -> None:
    """Only user and assistant texts are moderated."""
    model = stack.script.LoadedGuard(GuardNetwork(), GuardTokenizer())

    with pytest.raises(ValueError):
        stack.script.decide_qwenguard(model, {"messages": messages})


def test_gpu_memory_is_not_read_before_the_gpu_is_used(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Asking an idle server must not create a CUDA context."""
    monkeypatch.setattr(sys.modules["torch"].cuda, "is_initialized", lambda: False)

    assert stack.script.gpu_memory() is None


def test_the_prompt_is_prefilled_in_chunks_before_generation(
    stack: Stack, monkeypatch: pytest.MonkeyPatch
) -> None:
    """All but the last token go through the base network in chunks."""
    monkeypatch.setattr(stack.script, "PREFILL_CHUNK_TOKENS", 1)
    network = GuardNetwork()
    model = stack.script.LoadedGuard(network, GuardTokenizer())
    messages = [{"role": "user", "content": "q"}]

    stack.script.decide_qwenguard(model, {"messages": messages})

    assert network.chunks == [[1], [2]]
