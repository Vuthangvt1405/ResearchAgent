"""Flag risky code before the model's code runs without asking (AC11).

This is a speed bump, not a wall: the Docker sandbox is the real protection.
It reads the code with `ast`, so words inside strings and comments never count.
"""

import ast
import re

# Reasons shown to the user next to Run / Skip
SHELL = "runs a shell command"
DELETES = "deletes files"
MOVES = "moves files"
WRITES_OUTSIDE = "writes outside the project folder"
INSTALLS = "installs packages"
HIDDEN_CODE = "runs hidden code"
LOW_LEVEL = "low-level system access"
SENDS_DATA = "sends data out"
UNPARSEABLE = "couldn't check this code"

# Full names of risky calls, after resolving import aliases
CALLS = {
    "os.system": SHELL, "os.popen": SHELL, "os.posix_spawn": SHELL, "os.posix_spawnp": SHELL,
    "os.remove": DELETES, "os.unlink": DELETES, "os.rmdir": DELETES, "os.removedirs": DELETES,
    "shutil.rmtree": DELETES,
    "os.rename": MOVES, "os.renames": MOVES, "os.replace": MOVES, "shutil.move": MOVES,
    "eval": HIDDEN_CODE, "exec": HIDDEN_CODE, "compile": HIDDEN_CODE, "__import__": HIDDEN_CODE,
    "os.fork": LOW_LEVEL, "os.forkpty": LOW_LEVEL,
    "requests.post": SENDS_DATA, "requests.put": SENDS_DATA, "requests.patch": SENDS_DATA,
    "httpx.post": SENDS_DATA, "httpx.put": SENDS_DATA, "httpx.patch": SENDS_DATA,
}
CALL_PREFIXES = {"os.exec": SHELL, "os.spawn": SHELL, "subprocess.": SHELL, "importlib.": HIDDEN_CODE}
# Importing these is already risky
MODULES = {
    "subprocess": SHELL, "pty": SHELL, "ctypes": LOW_LEVEL, "importlib": HIDDEN_CODE,
    "smtplib": SENDS_DATA, "ftplib": SENDS_DATA,
}
# Methods that are risky on any object
DELETE_METHODS = {"unlink", "rmdir"}
# Methods risky only on a pathlib Path, because str.replace and DataFrame.rename are everyday code
PATH_MOVE_METHODS = {"rename", "replace"}
PATH_WRITE_METHODS = {"write_text", "write_bytes", "touch", "mkdir"}
SEND_METHODS = {"post", "put", "patch"}  # on a requests/httpx/aiohttp session
SEND_MODULES = {"requests", "httpx", "aiohttp"}
SOCKET_METHODS = {"bind", "listen"}

SHELL_CELL_MAGICS = ("%%bash", "%%sh", "%%cmd", "%%script", "%%system", "%%powershell")
SHELL_LINE_MAGICS = ("%system", "%sx", "%sc")
INSTALL_MAGICS = ("%pip", "%conda", "%mamba")
HIDDEN_MAGICS = ("%run", "%load", "%%writefile")
SHELL_ASSIGN_RE = re.compile(r"^[\w\s,\[\]()]+=\s*!")
DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _outside(path: str) -> bool:
    """An absolute path, a drive path, or one that climbs out with `..`."""
    parts = re.split(r"[\\/]", path)
    return path.startswith(("/", "\\")) or bool(DRIVE_RE.match(path)) or ".." in parts


def _magics(code: str, reasons: list[str]) -> str:
    """Note IPython ! and % lines, and replace them with `pass` so ast can read the rest."""
    lines = code.splitlines()
    first = lines[0].strip() if lines else ""
    if first.startswith(SHELL_CELL_MAGICS):
        reasons.append(SHELL)
        return ""
    if first.startswith(HIDDEN_MAGICS):
        reasons.append(HIDDEN_CODE)
    out = []
    for line in lines:
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        word = stripped.split(maxsplit=1)[0] if stripped else ""
        if stripped.startswith("!") or SHELL_ASSIGN_RE.match(stripped):
            reasons.append(SHELL)
            if re.search(r"!\s*(pip|conda|mamba|apt|apt-get)\b", stripped):
                reasons.append(INSTALLS)
        elif word in INSTALL_MAGICS:
            reasons.append(INSTALLS)
        elif word in SHELL_LINE_MAGICS:
            reasons.append(SHELL)
        elif word in HIDDEN_MAGICS:
            reasons.append(HIDDEN_CODE)
        elif not stripped.startswith("%"):
            out.append(line)
            continue
        out.append(indent + "pass")
    return "\n".join(out)


class _Checker(ast.NodeVisitor):
    def __init__(self):
        self.reasons: list[str] = []
        self.aliases: dict[str, str] = {}  # local name -> full dotted name
        self.modules: set[str] = set()

    def flag(self, reason: str) -> None:
        self.reasons.append(reason)

    # ---- imports ----

    def _imported(self, module: str) -> None:
        top = module.split(".")[0]
        self.modules.add(top)
        if top in MODULES:
            self.flag(MODULES[top])

    def visit_Import(self, node: ast.Import) -> None:
        for a in node.names:
            self._imported(a.name)
            self.aliases[a.asname or a.name.split(".")[0]] = a.name if a.asname else a.name.split(".")[0]
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        self._imported(module)
        for a in node.names:
            self.aliases[a.asname or a.name] = f"{module}.{a.name}"
        self.generic_visit(node)

    # ---- calls ----

    def full_name(self, node: ast.AST) -> str | None:
        """Dotted name of a call target with aliases resolved: sp.run -> subprocess.run."""
        if isinstance(node, ast.Name):
            return self.aliases.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            base = self.full_name(node.value)
            return f"{base}.{node.attr}" if base else None
        return None

    def is_path(self, node: ast.AST) -> bool:
        """`Path(...)`, `pathlib.Path(...)` or a name made from one."""
        if isinstance(node, ast.Call):
            name = self.full_name(node.func) or ""
            return name.split(".")[-1] in ("Path", "PurePath", "PosixPath", "WindowsPath")
        return False

    def visit_Call(self, node: ast.Call) -> None:
        name = self.full_name(node.func)
        if name:
            if name in CALLS:
                self.flag(CALLS[name])
            for prefix, reason in CALL_PREFIXES.items():
                if name.startswith(prefix):
                    self.flag(reason)
            if name == "getattr" and len(node.args) > 1 and not isinstance(node.args[1], ast.Constant):
                self.flag(HIDDEN_CODE)
            if name == "open":
                self._check_open(node)
        if isinstance(node.func, ast.Attribute):
            method, target = node.func.attr, node.func.value
            if method in DELETE_METHODS:
                self.flag(DELETES)
            if method in PATH_MOVE_METHODS and self.is_path(target):
                self.flag(MOVES)
            if method in PATH_WRITE_METHODS and self.is_path(target) and self._literal_outside(target.args[:1]):
                self.flag(WRITES_OUTSIDE)
            if method in SEND_METHODS and self.modules & SEND_MODULES:
                self.flag(SENDS_DATA)
            if method in SOCKET_METHODS and "socket" in self.modules:
                self.flag(LOW_LEVEL)
            if method.startswith(("to_", "save")) and self._literal_outside(node.args[:1]):
                self.flag(WRITES_OUTSIDE)  # df.to_csv("/etc/x"), plt.savefig("../x.png")
        self.generic_visit(node)

    @staticmethod
    def _literal_outside(args: list[ast.AST]) -> bool:
        return bool(args) and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str) and _outside(args[0].value)

    def _check_open(self, node: ast.Call) -> None:
        mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
        writing = isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(c in mode.value for c in "wax+")
        if writing and self._literal_outside(node.args[:1]):
            self.flag(WRITES_OUTSIDE)


def check(code: str) -> list[str]:
    """Reasons the code is risky, without duplicates; empty list = safe to auto-run."""
    reasons: list[str] = []
    python = _magics(code, reasons)
    try:
        tree = ast.parse(python)
    except SyntaxError:
        reasons.append(UNPARSEABLE)
    else:
        checker = _Checker()
        checker.visit(tree)
        reasons += checker.reasons
    return list(dict.fromkeys(reasons))
