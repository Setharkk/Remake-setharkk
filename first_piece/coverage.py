"""Bounded observed-label coverage, independent of probability calibration."""
import copy

from setharkk.contracts import counter
from .spherical import point


class CoverageLedger:
    def __init__(self, core, *, window=32, max_age=None, started_at=0):
        counter(window, "coverage window", minimum=1)
        counter(started_at, "coverage start")
        c = core.config
        self.reserved_slots = c["max_tasks"]*c["max_leaves"]*c["n_actions"]*window
        self.window = window
        self.max_age = max(4096, 4*self.reserved_slots) if max_age is None else max_age
        counter(self.max_age, "coverage age", minimum=1)
        counter(self.reserved_slots, "coverage reservation", minimum=1)
        if core.metrics(detailed=False)["reserved_record_slots"]+self.reserved_slots > c["record_budget"]:
            raise ValueError("Learning and coverage exceed the combined record budget")
        self.started_at = started_at
        self.buckets = {}

    def after_receipt(self, old_core, new_core, action, outcome):
        """Copy only written buckets; repartition retained real labels after splits."""
        new = copy.copy(self)
        new.buckets = dict(self.buckets)
        retired = ({leaf for leaf, _, _ in self.buckets
                    if new_core.nodes[leaf]["children"] is not None}
                   if new_core.admissions != old_core.admissions else set())
        moves = {}
        for key in [key for key in new.buckets if key[0] in retired] if retired else []:
            _, context, recorded_action = key
            for row in new.buckets.pop(key):
                target = (new_core._leaf(row[1]), context, recorded_action)
                moves.setdefault(target, []).append(row)
        for key, rows in moves.items():
            new.buckets[key] = sorted(rows, key=lambda row: row[0])[-self.window:]
        step = new_core.steps
        key = (new_core._leaf(old_core.state), old_core.context, action)
        rows = [row for row in new.buckets.get(key, [])
                if step-row[0] < self.max_age]
        rows.append([step, list(old_core.state), outcome])
        new.buckets[key] = rows[-self.window:]
        return new

    def counts(self, core, leaf, context, action):
        rows = [row for row in self.buckets.get((leaf, context, action), [])
                if core.steps-row[0] < self.max_age]
        return {"observations": len(rows),
                "positive_outcomes": sum(row[2] for row in rows),
                "oldest_observation_revision": rows[0][0] if rows else None,
                "newest_observation_revision": rows[-1][0] if rows else None}

    def checkpoint(self):
        return {"window": self.window, "max_age": self.max_age,
                "started_at": self.started_at,
                "buckets": {":".join(map(str, key)): copy.deepcopy(rows)
                            for key, rows in sorted(self.buckets.items())}}

    @classmethod
    def restore(cls, snapshot, core):
        if type(snapshot) is not dict or set(snapshot) != {"window", "max_age", "started_at", "buckets"}:
            raise ValueError("Invalid coverage checkpoint")
        new = cls(core, window=snapshot["window"], max_age=snapshot["max_age"],
                  started_at=snapshot["started_at"])
        if new.started_at > core.steps or type(snapshot["buckets"]) is not dict:
            raise ValueError("Invalid coverage boundary")
        seen, contexts = set(), {}
        for key, rows in snapshot["buckets"].items():
            if type(key) is not str:
                raise ValueError("Invalid coverage key")
            parts = key.split(":")
            if len(parts) != 3 or any(not p.isdecimal() or str(int(p)) != p for p in parts):
                raise ValueError("Noncanonical coverage key")
            leaf, context, action = map(int, parts)
            if (leaf not in core.nodes or core.nodes[leaf]["children"] is not None
                    or context not in core.contexts or not 0 <= action < core.config["n_actions"]
                    or type(rows) is not list or not 1 <= len(rows) <= new.window):
                raise ValueError("Coverage exceeds its scope or window")
            previous = new.started_at
            for row in rows:
                if type(row) is not list or len(row) != 3:
                    raise ValueError("Invalid observed coverage row")
                step = counter(row[0], "coverage observation", minimum=1)
                state = point(row[1])
                if (not previous < step <= core.steps or step in seen
                        or type(row[2]) is not int or row[2] not in (0, 1)
                        or core._leaf(state) != leaf):
                    raise ValueError("Coverage observation boundary differs")
                previous = step
                seen.add(step)
                contexts[context] = contexts.get(context, 0)+1
            new.buckets[(leaf, context, action)] = copy.deepcopy(rows)
        if len(seen) > new.reserved_slots or any(n > core.contexts[c] for c, n in contexts.items()):
            raise ValueError("Coverage contains more labels than actual exposure")
        return new
