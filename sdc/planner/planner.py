"""
SecureData Central -- Planner.

Executor de grafo de dependencia declarado explicitamente, com verificacao
semantica em cada passo (nao supoe sucesso so porque a chamada nao lancou).
Deliberadamente pequeno: NAO e um solver de planejamento automatico.

Uso tipico interno: o fluxo do sdc_get_context e decomposto em
retrieve -> resolve_recency -> assemble, cada passo verificado.
"""
from __future__ import annotations

from typing import Callable

from sdc.core.types import ActionResult, Goal, Task, TaskStatus, VerificationOutcome, new_id
from sdc.verification.engine import VerificationEngine


class Planner:
    def __init__(self, verification: VerificationEngine | None = None) -> None:
        self.verification = verification or VerificationEngine()
        self.goals: dict[str, Goal] = {}

    def new_goal(self, description: str) -> Goal:
        g = Goal(id=new_id("goal"), description=description)
        self.goals[g.id] = g
        return g

    def add_task(self, goal: Goal, description: str, depends_on: list[str] | None = None) -> Task:
        t = Task(id=new_id("task"), goal_id=goal.id, description=description, depends_on=depends_on or [])
        goal.tasks.append(t)
        return t

    def runnable_tasks(self, goal: Goal) -> list[Task]:
        done = {t.id for t in goal.tasks if t.status == TaskStatus.DONE}
        return [
            t for t in goal.tasks
            if t.status == TaskStatus.PENDING and all(d in done for d in t.depends_on)
        ]

    def run_task(self, task: Task, action_fn: Callable[[Task], ActionResult]) -> Task:
        task.status = TaskStatus.RUNNING
        result = action_fn(task)
        task.result = result
        outcome = self.verification.verify(result).outcome
        if outcome == VerificationOutcome.OK:
            task.status = TaskStatus.DONE
        else:
            # FAILED e UNKNOWN -> FAILED: honesto, forca decisao explicita
            # (retry/replan) em vez de avancar as cegas.
            task.status = TaskStatus.FAILED
        return task

    def run_all(self, goal: Goal, action_fn: Callable[[Task], ActionResult]) -> Goal:
        while True:
            runnable = self.runnable_tasks(goal)
            if not runnable:
                break
            for task in runnable:
                self.run_task(task, action_fn)
                if task.status == TaskStatus.FAILED:
                    return goal
        return goal

    @property
    def is_done(self):
        def _check(goal: Goal) -> bool:
            return all(t.status == TaskStatus.DONE for t in goal.tasks)
        return _check
