"""Static import boundary checks. Dynamic imports are forbidden in application sources."""

import ast
import sys
from pathlib import Path


def violations(path: str, source: str) -> list[str]:
    module = path.removesuffix(".py").replace("/", ".")
    package = module if module.endswith(".__init__") else module.rsplit(".", 1)[0]
    package = package.removesuffix(".__init__")
    errors = []
    for node in ast.walk(ast.parse(source)):
        imports = []
        if isinstance(node, ast.Import):
            imports = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                base = ".".join(parts[: len(parts) - node.level + 1] + ([base] if base else []))
            imports = [base + "." + alias.name for alias in node.names]
        elif isinstance(node, ast.Call) and (
            isinstance(node.func, ast.Name)
            and node.func.id == "__import__"
            or isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
        ):
            errors.append(f"{path}:{node.lineno}: dynamic imports are not allowed")
        for target in imports:
            root = target.split(".")[0]
            denied = root == "archive"
            if ".domain." in module:
                own = module.split(".domain.")[0] + ".domain"
                denied |= root not in sys.stdlib_module_names and not target.startswith(own + ".")
            if not module.startswith(("rpb.bootstrap.", "rpb.adapters.")):
                denied |= target.startswith(("rpb.adapters.", "rpb.bootstrap."))
            if ".application." in module:
                denied |= root in {"fastapi", "sqlalchemy", "psycopg", "uvicorn"}
                denied |= target.startswith("rpb.api.")
                if target.startswith("rpb.modules."):
                    owner = module.split(".")[2]
                    other = target.split(".")[2]
                    denied |= (
                        owner != other and f"rpb.modules.{other}.application.ports." not in target
                    )
            if module.startswith("rpb.knowledge."):
                denied |= target.startswith(("rpb.agents.", "rpb.modules.", "rpb.api."))
            if module.startswith("rpb.api.") and target.startswith("rpb.modules."):
                denied |= ".application." not in target
            if denied:
                errors.append(f"{path}:{node.lineno}: forbidden import {target}")
    return errors


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "backend/src"
    errors = [
        error
        for path in root.rglob("*.py")
        for error in violations(path.relative_to(root).as_posix(), path.read_text())
    ]
    if errors:
        raise SystemExit("\n".join(errors))
    print("Architecture imports passed (static imports; no business behavior inferred).")


if __name__ == "__main__":
    main()
