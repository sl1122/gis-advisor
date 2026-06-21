from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WorkflowStep:
    id: str
    title: str
    purpose: str
    engine: str
    algorithm: str
    inputs: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "purpose": self.purpose,
            "engine": self.engine,
            "algorithm": self.algorithm,
            "inputs": self.inputs,
            "parameters": self.parameters,
            "outputs": self.outputs,
            "checks": self.checks,
        }


@dataclass
class Workflow:
    task: str
    task_types: list[str]
    assumptions: list[str]
    missing_inputs: list[str]
    data_paths: list[Path]
    steps: list[WorkflowStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "task_types": self.task_types,
            "assumptions": self.assumptions,
            "missing_inputs": self.missing_inputs,
            "data_paths": [str(path) for path in self.data_paths],
            "steps": [step.to_dict() for step in self.steps],
        }

