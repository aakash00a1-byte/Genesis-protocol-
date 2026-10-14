"""Dependency graph for subtasks.

Supports ordering, cycle detection, and topological execution levels so
independent subtask levels can run in parallel (where safe).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from genesis.exceptions import CircularDependencyError


@dataclass
class DependencyGraph:
    """Directed acyclic graph of subtask ids."""

    edges: dict[str, list[str]] = field(default_factory=dict)

    def add_node(self, node_id: str) -> None:
        self.edges.setdefault(node_id, [])

    def add_edge(self, from_id: str, to_id: str) -> None:
        """`from_id` must complete before `to_id` starts."""
        self.add_node(from_id)
        self.add_node(to_id)
        if from_id not in self.edges[to_id]:
            self.edges[to_id].append(from_id)

    def depends_on(self, node_id: str) -> list[str]:
        return list(self.edges.get(node_id, []))

    def validate(self) -> None:
        """Raise CircularDependencyError on any cycle."""
        visited: dict[str, int] = {}

        def visit(node: str, stack: list[str]) -> None:
            state = visited.get(node, 0)
            if state == 2:  # fully processed
                return
            if state == 1:  # on the current stack -> cycle
                cycle = " -> ".join(stack + [node])
                raise CircularDependencyError(f"circular dependency: {cycle}")
            visited[node] = 1
            stack.append(node)
            for dep in self.edges.get(node, []):
                visit(dep, stack)
            stack.pop()
            visited[node] = 2

        for node in self.edges:
            visit(node, [])

    def levels(self) -> list[list[str]]:
        """Topological levels: tasks in the same level have no dependency
        between them and can run in parallel."""
        self.validate()
        indegree = {n: 0 for n in self.edges}
        dependents: dict[str, list[str]] = {n: [] for n in self.edges}
        for node, deps in self.edges.items():
            for dep in deps:
                indegree[node] += 1
                dependents[dep].append(node)

        remaining = set(self.edges)
        levels: list[list[str]] = []
        while remaining:
            ready = sorted(
                n for n in remaining if indegree.get(n, 0) == 0
            )
            if not ready:
                raise CircularDependencyError("graph has a cycle")
            levels.append(ready)
            for node in ready:
                for dependent in dependents.get(node, []):
                    indegree[dependent] -= 1
                remaining.discard(node)
        return levels