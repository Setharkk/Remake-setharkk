"""Trainable neuron/prototype positions and intrinsic hyperbolic layers."""
import torch
from torch import nn

from .geometry import DTYPE, centroid, exp_origin, project_ball, squared_distance

DIMENSION = 4
NEURONS = 8


class IntrinsicNetwork(nn.Module):
    def __init__(self, seed=0):
        super().__init__()
        rng = torch.Generator(device="cpu").manual_seed(seed)

        def points(shape):
            q = .35 * torch.randn((*shape, DIMENSION), generator=rng, dtype=DTYPE)
            return nn.Parameter(project_ball(exp_origin(q)))

        self.feature_points = points((3, 2))
        self.action_points = points((4,))
        self.neuron_keys = points((NEURONS,))
        self.neuron_values = points((NEURONS,))
        self.output_points = points((4, 2))
        self.temperature = .35  # Fixed scalar, not a trainable flat weight.
        self.output_temperature = .5

    def latent_states(self, observations, actions):
        indices = torch.arange(3, device=observations.device).unsqueeze(0)
        features = self.feature_points[indices, observations.long()]
        action = self.action_points[actions].unsqueeze(1)
        encoded = centroid(torch.cat((features, action), dim=1))
        distances = squared_distance(
            encoded.unsqueeze(1), self.neuron_keys.unsqueeze(0)
        )
        affinities = (-distances / self.temperature).softmax(-1)
        activated = centroid(self.neuron_values.unsqueeze(0), affinities)
        # Intrinsic residual connection: a two-point Lorentz centroid.
        following = centroid(torch.stack((encoded, activated), dim=1))
        return encoded, following

    def forward(self, observations, actions):
        _, following = self.latent_states(observations, actions)
        distances = squared_distance(
            following[:, None, None, :], self.output_points.unsqueeze(0)
        )
        # Class 0 and class 1 are themselves learned hyperbolic prototypes.
        return (distances[..., 0] - distances[..., 1]) / self.output_temperature

    @property
    def intrinsic_degrees_of_freedom(self):
        return sum(p.numel() // (DIMENSION + 1) * DIMENSION for p in self.parameters())

    @property
    def points_count(self):
        return sum(p.numel() // (DIMENSION + 1) for p in self.parameters())
