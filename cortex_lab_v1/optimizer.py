"""Adaptive optimization on a product of Lorentz hyperboloids."""
import math
import torch

from .geometry import (
    exp_at, lorentz_dot, parallel_transport, project_ball, riemannian_gradient,
)


class RiemannianAdam:
    """Per-point scalar second moments and parallel-transported first moments.

    Gradients are raised with the Lorentz metric and projected to tangent
    spaces. Updates use the exponential map, followed by a geodesic radius
    constraint. This is an adaptive manifold optimizer, not torch Adam
    followed by normalization of unconstrained weights.
    """
    def __init__(self, parameters, lr=.03, max_step=.1, radius=2.5):
        self.parameters = list(parameters)
        if (
            not self.parameters or min(lr, max_step, radius) <= 0
            or not all(math.isfinite(v) for v in (lr, max_step, radius))
        ):
            raise ValueError("Invalid manifold optimizer settings")
        self.lr, self.max_step, self.radius = lr, max_step, radius
        self.steps = 0
        self.state = [
            (torch.zeros_like(p), torch.zeros_like(p[..., 0]))
            for p in self.parameters
        ]

    def zero_grad(self):
        for p in self.parameters:
            p.grad = None

    @torch.no_grad()
    def step(self):
        count = self.steps + 1
        prepared = []
        gradient_norms = []
        for point, (moment, variance) in zip(self.parameters, self.state):
            if point.grad is None:
                prepared.append((point.detach().clone(), moment, variance))
                continue
            if not torch.isfinite(point.grad).all():
                raise FloatingPointError("Non-finite ambient gradient")
            gradient = riemannian_gradient(point, point.grad)
            norm_squared = lorentz_dot(gradient, gradient).clamp_min(0)
            if not torch.isfinite(gradient).all() or not torch.isfinite(norm_squared).all():
                raise FloatingPointError("Non-finite Riemannian gradient")
            gradient_norms.append(float(norm_squared.sqrt().max().cpu()))
            new_moment = .9 * moment + .1 * gradient
            new_variance = .999 * variance + .001 * norm_squared
            direction = -self.lr * (new_moment / (1 - .9 ** count)) / (
                (new_variance / (1 - .999 ** count)).sqrt().unsqueeze(-1) + 1e-8
            )
            length = lorentz_dot(direction, direction).clamp_min(0).sqrt()
            direction = direction * (
                self.max_step / length.clamp_min(1e-12)
            ).clamp_max(1).unsqueeze(-1)
            following = project_ball(exp_at(point, direction), self.radius)
            moved_moment = parallel_transport(point, following, new_moment)
            if not torch.isfinite(following).all() or not torch.isfinite(moved_moment).all():
                raise FloatingPointError("Non-finite manifold update")
            prepared.append((following, moved_moment, new_variance))
        # Validate every update before modifying any point.
        for point, (following, _, _) in zip(self.parameters, prepared):
            point.copy_(following)
        self.state = [(moment, variance) for _, moment, variance in prepared]
        self.steps = count
        result = max(gradient_norms, default=0.)
        if not math.isfinite(result):
            raise FloatingPointError("Non-finite gradient diagnostic")
        return result
