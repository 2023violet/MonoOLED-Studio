from __future__ import annotations

from scene import clamp_state, eval_do, init_state, when_match


class SceneRuntime:
    """Deterministic UI-state timeline runner; not an MCU simulator."""

    def __init__(self, scene: dict, logger=None):
        self.scene = scene
        self.logger = logger
        self.state: dict = {}
        self.elapsed = 0
        self.reset()

    def _log_diff(self, before: dict, *, source: str, elapsed: int) -> None:
        if self.logger is None:
            return
        for name in sorted(self.state):
            old = before.get(name)
            new = self.state.get(name)
            if old != new:
                self.logger.log(
                    'STATE', name=name, before=old, after=new,
                    source=source, elapsed=elapsed,
                )

    def _apply_set(self, values: dict, *, source: str, elapsed: int) -> None:
        before = dict(self.state)
        for name, value in values.items():
            if name not in self.scene['states']:
                raise KeyError(f'timeline referenced unknown state: {name}')
            self.state[name] = value
        clamp_state(self.scene, self.state)
        self._log_diff(before, source=source, elapsed=elapsed)

    def _apply_do(self, expr: str, *, source: str, elapsed: int) -> None:
        before = dict(self.state)
        eval_do(expr, self.state)
        clamp_state(self.scene, self.state)
        self._log_diff(before, source=source, elapsed=elapsed)

    def reset(self) -> dict:
        self.state = init_state(self.scene)
        self.elapsed = 0
        for action in self.scene.get('timeline', []):
            if action.get('at') == 0 and 'set' in action:
                self._apply_set(action['set'], source='timeline:at=0', elapsed=0)
        clamp_state(self.scene, self.state)
        if self.logger is not None:
            self.logger.log('RESET', elapsed=0, state=dict(sorted(self.state.items())))
        return dict(self.state)

    def set_state(self, name: str, value) -> None:
        if name not in self.scene['states']:
            raise KeyError(f'unknown state: {name}')
        before = dict(self.state)
        self.state[name] = value
        clamp_state(self.scene, self.state)
        self._log_diff(before, source='manual', elapsed=self.elapsed)

    def step(self, amount: int = 1) -> dict:
        if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
            raise ValueError('step amount must be a non-negative integer')
        for _ in range(amount):
            now = self.elapsed + 1

            # Recurring actions observe the state that existed during the
            # preceding timeline step. This keeps a newly-entered state at its
            # initial value for one full timeline step before recurring actions run.
            for action in self.scene.get('timeline', []):
                every = action.get('every')
                if every is None:
                    continue
                every = int(every)
                if every <= 0 or now % every != 0:
                    continue
                if not when_match(action.get('when'), self.state):
                    continue
                if 'do' in action:
                    self._apply_do(action['do'], source=f'timeline:every={every}', elapsed=now)
                elif 'set' in action:
                    self._apply_set(action['set'], source=f'timeline:every={every}', elapsed=now)

            for action in self.scene.get('timeline', []):
                if action.get('at') != now:
                    continue
                if 'set' in action:
                    self._apply_set(action['set'], source=f'timeline:at={now}', elapsed=now)
                elif 'do' in action:
                    self._apply_do(action['do'], source=f'timeline:at={now}', elapsed=now)

            self.elapsed = now
        return dict(self.state)
