import json
from hashlib import sha256
import re
from pathlib import Path
import sys
from atomic_io import atomic_write_json


def runtime_paths(*, module_file=None, frozen=None, meipass=None, executable=None):
    """Resolve application-owned paths without assuming POSIX or Windows literals."""
    module_file = Path(module_file or __file__).resolve()
    frozen = bool(getattr(sys, 'frozen', False)) if frozen is None else bool(frozen)
    if frozen:
        bundle_root = Path(meipass or getattr(sys, '_MEIPASS', module_file.parent)).resolve()
        exe = Path(executable or sys.executable).resolve()
        return bundle_root, bundle_root / 'src' / 'scenes', exe.parent / 'logs'
    root = module_file.parent.parent
    return root, module_file.parent / 'scenes', module_file.parent / 'logs'


ROOT, SCENES_DIR, LOGS_DIR = runtime_paths()


def _scene_path(name) -> Path:
    candidate = Path(name)
    if candidate.exists() or candidate.is_absolute() or candidate.suffix.lower() == '.json' and candidate.parent != Path('.'):
        return candidate.resolve()
    if str(name).endswith('.json'):
        return (SCENES_DIR / str(name)).resolve()
    return (SCENES_DIR / f'{name}.json').resolve()


def load_scene(name='main_scene', *, project_root=None):
    path = _scene_path(name)
    raw_bytes = path.read_bytes()
    scene = json.loads(raw_bytes.decode('utf-8'))

    if project_root is not None:
        root = Path(project_root).resolve()
    elif scene.get('project_root'):
        raw_root = Path(str(scene['project_root']))
        root = (path.parent / raw_root).resolve() if not raw_root.is_absolute() else raw_root.resolve()
    elif path.parent.resolve() == SCENES_DIR.resolve():
        root = ROOT.resolve()
    else:
        root = path.parent.resolve()

    scene['_path'] = str(path)
    scene['_root'] = str(root)
    scene['_disk_path'] = str(path.resolve())
    scene['_disk_sha256'] = sha256(raw_bytes).hexdigest()
    return scene


def save_scene(scene):
    path = Path(scene['_path'])
    data = {k: v for k, v in scene.items() if not str(k).startswith('_')}
    atomic_write_json(path,data)


def scene_root(scene=None) -> Path:
    if scene and scene.get('_root'):
        return Path(scene['_root']).resolve()
    return ROOT.resolve()


def resolve(p, *, scene=None):
    path = Path(p)
    if path.is_absolute():
        return path.resolve()
    return (scene_root(scene) / path).resolve()


def init_state(scene):
    st = {}
    for k, spec in scene['states'].items():
        st[k] = spec['init']
    return dict(st)


def clamp_state(scene, state):
    for k, spec in scene['states'].items():
        v = state[k]
        if spec['type'] == 'int':
            if 'values' in spec:
                if v not in spec.get('values', []):
                    v = spec['init']
            else:
                v = max(spec.get('min', 0), min(spec.get('max', 10 ** 9), int(v)))
        else:
            if v not in spec['values']:
                v = spec['init']
        state[k] = v
    return state


_DO_RE = re.compile(r'^(\w+)\s*(\+=|-=|=)\s*(-?\d+)$')


def eval_do(expr, state):
    m = _DO_RE.match(expr.strip())
    if not m:
        raise ValueError(f'不支持的 timeline 表达式: {expr!r}（仅支持 var = n / += n / -= n）')
    name, op, num = m.group(1), m.group(2), int(m.group(3))
    if name not in state:
        raise KeyError(f'timeline 引用了未定义的状态变量: {name}')
    cur = state[name]
    state[name] = cur + num if op == '+=' else cur - num if op == '-=' else num


def subst(text, state, lower=False):
    def rep(m):
        v = str(state[m.group(1)])
        return v.lower() if lower else v
    return re.sub(r'\{(\w+)\}', rep, text)


def when_match(when, state):
    if not when:
        return True
    return all(state[k] == v for k, v in when.items())
