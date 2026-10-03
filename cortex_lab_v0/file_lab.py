"""Real operations on fresh files owned by each experiment."""
from pathlib import Path

ACTION_NAMES = ("create", "move", "rename", "read")


class FileLab:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=False)
        self.count = 0

    def execute(self, state, action):
        if len(state) != 3 or any(bit not in (0, 1) for bit in state):
            raise ValueError("A state must contain three binary existence bits")
        if action not in range(len(ACTION_NAMES)):
            raise ValueError("Unknown action")
        self.count += 1
        case = self.root / f"case_{self.count:06d}"
        (case / "A").mkdir(parents=True)
        (case / "B").mkdir()
        source = case / "A" / "item.txt"
        destination = case / "B" / "item.txt"
        renamed = case / "A" / "renamed.txt"
        paths = (source, destination, renamed)
        for bit, path in zip(state, paths):
            if bit:
                path.write_text("cortex-lab\n", encoding="utf-8")
        error = None
        bytes_read = None
        try:
            if action == 0:
                with source.open("x", encoding="utf-8") as handle:
                    handle.write("cortex-lab\n")
            elif action == 1:
                # Explicitly make no-overwrite semantics identical on
                # Windows and POSIX. Both outcomes are learned by the model.
                if destination.exists():
                    raise FileExistsError("Destination already exists")
                source.rename(destination)
            elif action == 2:
                if renamed.exists():
                    raise FileExistsError("Renamed file already exists")
                source.rename(renamed)
            else:
                bytes_read = len(source.read_bytes())
            success = 1
        except OSError as exc:
            success = 0
            error = type(exc).__name__
        after = [int(path.is_file()) for path in paths]
        result = after + [success]
        return result, {
            "state": list(state),
            "action": ACTION_NAMES[action],
            "result": result,
            "error": error,
            "bytes_read": bytes_read,
            "directory": str(case),
        }


def collect_cases(lab):
    cases = []
    for action in range(len(ACTION_NAMES)):
        for value in range(8):
            state = [(value >> bit) & 1 for bit in range(3)]
            result, _ = lab.execute(state, action)
            cases.append({"state": state, "action": action, "result": result})
    return cases
