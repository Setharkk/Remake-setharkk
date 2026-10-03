"""Small, parameter-matched curved/flat transition models.

An ensemble is a heuristic approximation of uncertainty, not a calibrated
Bayesian posterior. All outputs describe observable filesystem results.
"""
import itertools
import random
from collections import deque

import torch
from torch import nn
from torch.nn import functional as F

DTYPE = torch.float64
EPS = 1e-12
LATENT = 4
OBSERVATIONS = 3
ACTIONS = 4
OUTPUTS = 4


def lorentz_dot(x, y):
    return -(x[..., :1] * y[..., :1]).sum(-1) + (
        x[..., 1:] * y[..., 1:]
    ).sum(-1)


def exp_origin(q):
    r = (q.square().sum(-1, keepdim=True) + EPS).sqrt()
    return torch.cat((r.cosh(), (r.sinh() / r) * q), dim=-1)


def log_origin(z):
    r = (z[..., 1:].square().sum(-1, keepdim=True) + EPS).sqrt()
    return (r.asinh() / r) * z[..., 1:]


def transport_from_origin(z, w):
    inner = (z[..., 1:] * w).sum(-1, keepdim=True)
    return torch.cat(
        (inner, w + inner * z[..., 1:] / (1 + z[..., :1])), dim=-1
    )


def curved_step(z, w):
    v = transport_from_origin(z, w)
    # Parallel transport preserves the tangent norm. Using ||w|| avoids
    # cancellation in the Lorentz norm near the origin.
    r = (w.square().sum(-1, keepdim=True) + EPS).sqrt()
    return r.cosh() * z + (r.sinh() / r) * v


class TransitionModel(nn.Module):
    def __init__(self, geometry):
        super().__init__()
        if geometry not in ("hyperbolic", "euclidean"):
            raise ValueError("Unknown geometry")
        self.geometry = geometry
        self.encoder = nn.Linear(OBSERVATIONS, LATENT, dtype=DTYPE)
        self.transition = nn.Linear(LATENT + ACTIONS, LATENT, dtype=DTYPE)
        self.decoder = nn.Linear(LATENT, OUTPUTS, dtype=DTYPE)

    def forward(self, observations, actions):
        q = 0.8 * torch.tanh(self.encoder(observations))
        action_bits = F.one_hot(actions, ACTIONS).to(DTYPE)
        w = 0.4 * torch.tanh(
            self.transition(torch.cat((q, action_bits), dim=-1))
        )
        if self.geometry == "hyperbolic":
            next_q = log_origin(curved_step(exp_origin(q), w))
        else:
            next_q = q + w
        return self.decoder(next_q)


def information_gain(probabilities):
    """Information about a uniformly chosen ensemble member.

    Each member predicts independent Bernoulli output bits. Enumerating all
    16 joint outcomes computes the ensemble mixture entropy exactly for
    that assumption. The ensemble itself remains a posterior approximation.
    Shape: members x candidates x output_bits -> candidates.
    """
    bits = torch.tensor(
        list(itertools.product((False, True), repeat=OUTPUTS)),
        device=probabilities.device, dtype=torch.bool
    )
    p = probabilities.clamp(1e-9, 1 - 1e-9).unsqueeze(-2)
    joint = torch.where(bits, p, 1 - p).prod(-1)

    def entropy(values):
        return -(values * values.clamp_min(EPS).log()).sum(-1)

    return (entropy(joint.mean(0)) - entropy(joint).mean(0)).clamp_min(0)


class Ensemble:
    def __init__(self, geometry, seed, device="cpu", members=3):
        self.device = torch.device(device)
        self.models = []
        for index in range(members):
            # Initialize the matching geometries identically on CPU.
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(seed + index * 997)
                model = TransitionModel(geometry)
            self.models.append(model.to(self.device))
        self.optimizers = [
            torch.optim.Adam(model.parameters(), lr=0.025, weight_decay=1e-4)
            for model in self.models
        ]
        self.rngs = [random.Random(seed + index * 2017) for index in range(members)]
        self.memory = deque(maxlen=2048)
        self.initial = [self._vector(model).clone() for model in self.models]
        self.updates = 0
        self.last_loss = 0.0
        self.last_gradient = 0.0

    @staticmethod
    def _vector(model):
        return torch.cat([p.detach().flatten() for p in model.parameters()])

    def inputs(self, candidates):
        observations = torch.tensor(
            [entry["state"] for entry in candidates],
            dtype=DTYPE, device=self.device
        )
        actions = torch.tensor(
            [entry["action"] for entry in candidates],
            dtype=torch.long, device=self.device
        )
        return observations, actions

    @torch.no_grad()
    def predict(self, candidates):
        observations, actions = self.inputs(candidates)
        return torch.stack([
            model(observations, actions).sigmoid() for model in self.models
        ])

    def observe(self, state, action, result):
        self.memory.append({
            "state": list(state), "action": int(action), "result": list(result)
        })

    def learn(self, updates=3, batch_size=32):
        if not self.memory:
            return
        losses, gradients = [], []
        for _ in range(updates):
            for model, optimizer, rng in zip(
                self.models, self.optimizers, self.rngs
            ):
                batch = [rng.choice(self.memory) for _ in range(batch_size)]
                observations, actions = self.inputs(batch)
                targets = torch.tensor(
                    [entry["result"] for entry in batch],
                    dtype=DTYPE, device=self.device
                )
                optimizer.zero_grad(set_to_none=True)
                loss = F.binary_cross_entropy_with_logits(
                    model(observations, actions), targets
                )
                if not torch.isfinite(loss):
                    raise FloatingPointError("Non-finite training loss")
                loss.backward()
                gradient = torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
                if not torch.isfinite(gradient):
                    raise FloatingPointError("Non-finite gradient")
                optimizer.step()
                self.updates += 1
                losses.append(float(loss.detach().cpu()))
                gradients.append(float(gradient.detach().cpu()))
        self.last_loss = sum(losses) / len(losses)
        self.last_gradient = sum(gradients) / len(gradients)

    @torch.no_grad()
    def evaluate(self, cases):
        probabilities = self.predict(cases)
        targets = torch.tensor(
            [entry["result"] for entry in cases],
            dtype=DTYPE, device=self.device
        )
        mean = probabilities.mean(0)
        mixture_likelihood = torch.where(
            targets.bool(), probabilities, 1 - probabilities
        ).prod(-1).mean(0)
        changes = [
            float((self._vector(model) - initial).norm().cpu())
            for model, initial in zip(self.models, self.initial)
        ]
        metrics = {
            "brier": float((mean - targets).square().mean().cpu()),
            "nll": float(-mixture_likelihood.clamp_min(EPS).log().mean().cpu()),
            "exact_accuracy": float(
                (mean.ge(0.5) == targets.bool()).all(-1).to(DTYPE).mean().cpu()
            ),
            "success_accuracy": float(
                (mean[:, -1].ge(0.5) == targets[:, -1].bool()).to(DTYPE).mean().cpu()
            ),
            "weights_changed_l2": sum(changes) / len(changes),
            "gradient_norm": self.last_gradient,
            "train_loss": self.last_loss,
            "optimizer_updates": self.updates,
        }
        for action in range(ACTIONS):
            indices = [i for i, case in enumerate(cases) if case["action"] == action]
            if indices:
                metrics[f"brier_action_{action}"] = float(
                    (mean[indices] - targets[indices]).square().mean().cpu()
                )
        return metrics

    def checkpoint(self):
        return [
            {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
            for model in self.models
        ]
