from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    id: str
    default_shortcut: str = ''
    label_key: str = ''


class ShortcutConflictError(ValueError):
    pass


def normalize_shortcut(value: str) -> str:
    return str(value or '').strip()


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._bindings: dict[str, str] = {}

    def register(self, command_id: str, *, shortcut: str = '', label_key: str = '') -> Command:
        if command_id in self._commands:
            raise KeyError(command_id)
        cmd = Command(command_id, normalize_shortcut(shortcut), label_key)
        self._commands[command_id] = cmd
        if shortcut:
            self.bind(command_id, shortcut)
        return cmd

    @staticmethod
    def _validate_bindings(mapping: dict[str, str]) -> None:
        seen: dict[str, str] = {}
        for command_id, shortcut in mapping.items():
            normalized = normalize_shortcut(shortcut).casefold()
            if not normalized:
                continue
            if normalized in seen and seen[normalized] != command_id:
                raise ShortcutConflictError(f'{shortcut} already bound to {seen[normalized]}')
            seen[normalized] = command_id

    def bind(self, command_id: str, shortcut: str) -> None:
        if command_id not in self._commands:
            raise KeyError(command_id)
        candidate = dict(self._bindings)
        candidate[command_id] = normalize_shortcut(shortcut)
        self._validate_bindings(candidate)
        self._bindings = candidate

    def apply_bindings(self, mapping: dict[str, str], *, ignore_unknown: bool = True) -> None:
        """Apply multiple user bindings atomically.

        Conflict validation happens before mutating the live registry so a bad
        Preferences edit cannot leave half the QAction set updated.
        """
        candidate = dict(self._bindings)
        for command_id, shortcut in mapping.items():
            if command_id not in self._commands:
                if ignore_unknown:
                    continue
                raise KeyError(command_id)
            candidate[command_id] = normalize_shortcut(shortcut)
        self._validate_bindings(candidate)
        self._bindings = candidate


    def apply_bindings_best_effort(self, mapping: dict[str, str], *, ignore_unknown: bool = True):
        """Apply valid custom bindings without discarding unrelated choices.

        Mapping order is deterministic.  A conflicting entry is rejected and the
        previous binding for that command remains unchanged.
        """
        accepted: dict[str, str] = {}
        rejected: dict[str, str] = {}
        for command_id, shortcut in mapping.items():
            if command_id not in self._commands:
                if ignore_unknown:
                    continue
                rejected[command_id] = 'unknown command'
                continue
            try:
                self.bind(command_id, shortcut)
            except ShortcutConflictError as exc:
                rejected[command_id] = str(exc)
            else:
                accepted[command_id] = normalize_shortcut(shortcut)
        return accepted, rejected

    def shortcut(self, command_id: str) -> str:
        return self._bindings.get(command_id, self._commands[command_id].default_shortcut)

    def bindings(self) -> dict[str, str]:
        return {command.id: self.shortcut(command.id) for command in self.commands()}

    def commands(self) -> tuple[Command, ...]:
        return tuple(self._commands.values())
