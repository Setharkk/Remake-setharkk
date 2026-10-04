"""Lorentz geometry at curvature -1; float64 coordinates in R^(d+1)."""
import torch

DTYPE = torch.float64


def lorentz_dot(x, y):
    return -(x[..., :1] * y[..., :1]).sum(-1) + (x[..., 1:] * y[..., 1:]).sum(-1)


def _cosh_sinhc(s):
    r = s.clamp_min(1e-6).sqrt()
    cosh = 1 + s * (.5 + s * (1 / 24 + s / 720))
    sinhc = 1 + s * (1 / 6 + s * (1 / 120 + s / 5040))
    return torch.where(s < 1e-6, cosh, r.cosh()), torch.where(
        s < 1e-6, sinhc, r.sinh() / r
    )


def exp_origin(q):
    cosh, sinhc = _cosh_sinhc(q.square().sum(-1, keepdim=True))
    return torch.cat((cosh, sinhc * q), dim=-1)


def squared_distance(x, y):
    # acosh(1+u)^2 has an analytic limit at u=0, unlike acosh itself.
    u = (-lorentz_dot(x, y) - 1).clamp_min(0)
    series = u * (2 + u * (-1 / 3 + u * (4 / 45 - u / 35)))
    regular = (1 + u.clamp_min(1e-4)).acosh().square()
    return torch.where(u < 1e-4, series, regular)


def tangent_projection(point, vector):
    return vector + lorentz_dot(point, vector).unsqueeze(-1) * point


def riemannian_gradient(point, ambient_gradient):
    raised = ambient_gradient.clone()
    raised[..., 0] *= -1
    return tangent_projection(point, raised)


def exp_at(point, tangent):
    s = lorentz_dot(tangent, tangent).clamp_min(0).unsqueeze(-1)
    cosh, sinhc = _cosh_sinhc(s)
    return cosh * point + sinhc * tangent


def parallel_transport(source, destination, tangent):
    coefficient = lorentz_dot(destination, tangent) / (
        1 - lorentz_dot(source, destination)
    )
    transported = tangent + coefficient.unsqueeze(-1) * (source + destination)
    return tangent_projection(destination, transported)


def centroid(points, weights=None):
    """Minimizer of sum_i weight_i*cosh(distance(z, point_i)).

    This Lorentz centroid is not generally the squared-distance Frechet mean.
    Weights must be positive; the network uses uniform weights or softmax.
    """
    total = points.sum(-2) if weights is None else (
        points * weights.unsqueeze(-1)
    ).sum(-2)
    norm = (-lorentz_dot(total, total)).sqrt().unsqueeze(-1)
    return total / norm


def project_ball(point, radius=2.5):
    """Geodesic projection to a ball at the origin and roundoff repair."""
    spatial = point[..., 1:]
    norm = spatial.square().sum(-1, keepdim=True).sqrt()
    bound = torch.sinh(torch.as_tensor(radius, dtype=point.dtype, device=point.device))
    scale = (bound / norm.clamp_min(1e-12)).clamp_max(1)
    spatial = spatial * scale
    time = (1 + spatial.square().sum(-1, keepdim=True)).sqrt()
    return torch.cat((time, spatial), dim=-1)
