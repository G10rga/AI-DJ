"""Versioned plan contract. All times are seconds; beat/bar indices are zero-based."""
from dataclasses import asdict, dataclass
import json
import math


@dataclass(frozen=True)
class Excerpt:
    track_id: str
    source_in: float
    source_out: float
    source_duration: float
    source_bpm: float
    target_bpm: float

    @property
    def output_duration(self):
        return (self.source_out - self.source_in) * self.source_bpm / self.target_bpm

    def validate(self):
        numbers = (self.source_in, self.source_out, self.source_duration, self.source_bpm, self.target_bpm)
        if not self.track_id or not all(math.isfinite(v) for v in numbers):
            raise ValueError("Invalid excerpt values")
        if not 0 <= self.source_in < self.source_out <= self.source_duration:
            raise ValueError("Excerpt exceeds source bounds")
        if min(self.source_bpm, self.target_bpm) <= 0:
            raise ValueError("Tempo must be positive")


@dataclass(frozen=True)
class Transition:
    style: str
    overlap_seconds: float
    bars: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MixPlan:
    mix_id: str
    revision: int
    excerpts: tuple[Excerpt, ...]
    transitions: tuple[Transition, ...]
    sample_rate: int = 44100
    schema_version: int = 1

    def validate(self):
        if self.schema_version != 1 or not self.mix_id or self.revision < 1:
            raise ValueError("Invalid plan identity or schema")
        if not self.excerpts or len(self.transitions) != len(self.excerpts) - 1:
            raise ValueError("A plan needs one transition per adjacent pair")
        if self.sample_rate not in {44100, 48000}:
            raise ValueError("Unsupported output sample rate")
        ids = [e.track_id for e in self.excerpts]
        if len(ids) != len(set(ids)):
            raise ValueError("Each uploaded entry must appear once")
        for excerpt in self.excerpts:
            excerpt.validate()
        for transition in self.transitions:
            if transition.style not in {"eq_cut", "smooth", "boundary_fade", "controlled", "phrase_cut"}:
                raise ValueError("Unknown transition style")
            if not math.isfinite(transition.overlap_seconds) or transition.overlap_seconds <= 0:
                raise ValueError("Overlap must be finite and positive")
            if transition.bars < 0:
                raise ValueError("Bar count must be nonnegative")
            if transition.style == 'controlled' and transition.bars != 16:
                raise ValueError('Controlled blends require sixteen bars')
            if transition.style == 'phrase_cut' and (transition.bars != 0 or transition.overlap_seconds > .05):
                raise ValueError('Phrase cuts require a click-free exchange of at most 50ms')
        for index, excerpt in enumerate(self.excerpts):
            incoming = self.transitions[index - 1].overlap_seconds if index else 0
            outgoing = self.transitions[index].overlap_seconds if index < len(self.transitions) else 0
            if incoming + outgoing >= excerpt.output_duration:
                raise ValueError("Transitions consume the entire excerpt")

    def to_json(self):
        self.validate()
        return json.dumps(asdict(self), allow_nan=False, sort_keys=True)

    @classmethod
    def from_json(cls, value: str):
        data = json.loads(value)
        data["excerpts"] = tuple(Excerpt(**e) for e in data["excerpts"])
        data["transitions"] = tuple(
            Transition(**{**t, "warnings": tuple(t["warnings"])}) for t in data["transitions"]
        )
        plan = cls(**data)
        plan.validate()
        return plan
