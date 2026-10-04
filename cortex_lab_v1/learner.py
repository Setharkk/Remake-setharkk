"""Online learning with manifold parameters and manifold optimizer states."""
import math
import random
from collections import deque

import torch
from torch.nn import functional as F

from cortex_lab_v0.core import information_gain, mixture_log_likelihood
from .geometry import DTYPE, lorentz_dot, squared_distance
from .network import IntrinsicNetwork
from .optimizer import RiemannianAdam


class IntrinsicEnsemble:
    def __init__(self, seed=0, members=3, device="cpu", lr=.03):
        if members < 1:
            raise ValueError("At least one ensemble member is required")
        self.device = torch.device(device)
        self.models = [
            IntrinsicNetwork(seed + i * 997).to(self.device) for i in range(members)
        ]
        self.optimizers = [
            RiemannianAdam(model.parameters(), lr=lr) for model in self.models
        ]
        self.rngs = [random.Random(seed + i * 2017) for i in range(members)]
        self.memory = deque(maxlen=2048)
        self.initial = [
            [p.detach().clone() for p in model.parameters()] for model in self.models
        ]
        self.updates = 0
        self.last_loss = 0.
        self.last_gradient = 0.

    def inputs(self, cases):
        return (
            torch.tensor([c["state"] for c in cases], dtype=DTYPE, device=self.device),
            torch.tensor([c["action"] for c in cases], dtype=torch.long, device=self.device),
        )

    @torch.no_grad()
    def predict(self, cases):
        observations, actions = self.inputs(cases)
        return torch.stack([model(observations, actions).sigmoid() for model in self.models])

    def observe(self, state, action, result):
        self.memory.append({
            "state": list(state), "action": int(action), "result": list(result)
        })

    def learn(self, updates=3, batch_size=32):
        if min(updates, batch_size) < 1:
            raise ValueError("Update counts must be positive")
        if not self.memory:
            return
        losses, norms = [], []
        for _ in range(updates):
            for model, optimizer, rng in zip(self.models, self.optimizers, self.rngs):
                batch = [rng.choice(self.memory) for _ in range(batch_size)]
                observations, actions = self.inputs(batch)
                targets = torch.tensor(
                    [c["result"] for c in batch], dtype=DTYPE, device=self.device
                )
                optimizer.zero_grad()
                loss = F.binary_cross_entropy_with_logits(model(observations, actions), targets)
                if not torch.isfinite(loss):
                    raise FloatingPointError("Non-finite learning loss")
                loss.backward()
                norms.append(optimizer.step())
                losses.append(float(loss.detach().cpu()))
                self.updates += 1
        self.last_loss = sum(losses) / len(losses)
        self.last_gradient = sum(norms) / len(norms)

    @torch.no_grad()
    def evaluate(self, cases):
        observations, actions = self.inputs(cases)
        logits = torch.stack([model(observations, actions) for model in self.models])
        probabilities = logits.sigmoid()
        targets = torch.tensor([c["result"] for c in cases], dtype=DTYPE, device=self.device)
        mean = probabilities.mean(0)
        displacement = torch.cat([
            squared_distance(p, initial).sqrt().flatten()
            for model, originals in zip(self.models, self.initial)
            for p, initial in zip(model.parameters(), originals)
        ])
        constraints = torch.cat([
            (lorentz_dot(p, p) + 1).abs().flatten()
            for model in self.models for p in model.parameters()
        ])
        metrics = {
            "brier": float((mean - targets).square().mean().cpu()),
            "nll": float(-mixture_log_likelihood(logits, targets).mean().cpu()),
            "exact_accuracy": float(
                (mean.ge(.5) == targets.bool()).all(-1).to(DTYPE).mean().cpu()
            ),
            "success_accuracy": float(
                (mean[:, -1].ge(.5) == targets[:, -1].bool()).to(DTYPE).mean().cpu()
            ),
            "geodesic_parameter_displacement": float(displacement.mean().cpu()),
            "max_manifold_constraint_error": float(constraints.max().cpu()),
            "riemannian_gradient_norm": self.last_gradient,
            "train_loss": self.last_loss, "optimizer_updates": self.updates,
        }
        for action in range(4):
            indices = [i for i, case in enumerate(cases) if case["action"] == action]
            if indices:
                metrics[f"brier_action_{action}"] = float(
                    (mean[indices] - targets[indices]).square().mean().cpu()
                )
        if not all(math.isfinite(v) for v in metrics.values()):
            raise FloatingPointError("Non-finite evaluation")
        return metrics

    def checkpoint(self):
        return {
            "format_version": 1, "architecture": "intrinsic_lorentz_prototypes",
            "dimension": 4, "points_per_model": 34,
            "intrinsic_degrees_of_freedom_per_model": 136,
            "stored_scalars_per_model": 170,
            "models": [
                {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                for model in self.models
            ],
        }

    def load_weights(self, checkpoint):
        """Restore inference weights into a fresh learner; not optimizer resume."""
        if self.updates or self.memory:
            raise ValueError("Load weights into a fresh learner")
        if (
            checkpoint.get("format_version") != 1
            or checkpoint.get("architecture") != "intrinsic_lorentz_prototypes"
            or checkpoint.get("dimension") != 4
            or len(checkpoint.get("models", [])) != len(self.models)
        ):
            raise ValueError("Incompatible intrinsic checkpoint")
        # Validate the complete payload before mutating any model.
        for model, state in zip(self.models, checkpoint["models"]):
            expected = model.state_dict()
            if set(state) != set(expected):
                raise ValueError("Checkpoint parameter names differ")
            for name, value in state.items():
                if (
                    not isinstance(value, torch.Tensor)
                    or value.shape != expected[name].shape or value.dtype != DTYPE
                ):
                    raise ValueError("Checkpoint parameter shape or dtype differs")
                if (
                    not torch.isfinite(value).all() or not (value[..., 0] > 0).all()
                    or (lorentz_dot(value, value) + 1).abs().max() > 1e-8
                    or value[..., 1:].square().sum(-1).sqrt().asinh().max() > 2.5 + 1e-8
                ):
                    raise ValueError("Checkpoint points violate the manifold or radius")
        for model, state in zip(self.models, checkpoint["models"]):
            model.load_state_dict(state)
        self.initial = [
            [p.detach().clone() for p in model.parameters()] for model in self.models
        ]
