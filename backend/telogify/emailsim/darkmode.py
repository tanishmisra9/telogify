"""Measured Gmail iOS app dark-mode color transform.

DARK_MODE_SAMPLES is real measured data, not a guessed formula: 74 (input_hex -> dark_hex) pairs
captured from Probe A screenshots (Gmail iOS app, light vs dark, both light-theme readings
verified pixel-exact against the known input first) on 2026-08-01, plus a supplemental probe
sent the same day for the 6 2026-season team colors the original probe missed (Alpine, RB, Haas,
Kick Sauber, Audi, Cadillac) -- without them, an insight card border/badge in any of those teams'
colors nearest-neighbor-extrapolated to a wildly wrong result (Cadillac's `#E8A33D` landed on
`#303e07`, a near-invisible dark olive, purely because it happened to be geometrically closest to
an unrelated calibration point; the real measured result is `#6d4c1c`, a plainly visible dark
gold). Desktop Gmail's dark toggle was confirmed inert on this account (every desktop screenshot
read as light regardless of macOS appearance), so this transform is iOS-app-specific -- see the
emailsim plan and PROFILE_IOS_DARK in profiles.py.

ColorTransform wraps this as a nearest-neighbor lookup in RGB space via a KD-tree: for a color
outside the 74 measured samples, it returns the measured dark-mode result of whichever sample is
closest in Euclidean RGB distance. This is deliberately not a fitted analytic curve (e.g. a
single global "invert lightness" formula) because the measured data itself isn't one -- a
solid grayscale ramp inverts on a smooth curve, but the same-lightness *team colors* (blue, red,
teal, orange, green, sky-blue) shifted far less than the near-white/near-black brand swatches did
at a similar lightness, which a single global formula would get wrong for exactly the colors the
digest actually ships. Nearest-neighbor lets the real, uneven measured behavior stand.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

DARK_MODE_SAMPLES: dict[str, str] = {
    "#000000": "#ffffff",
    "#0b0b0b": "#f5f5f5",
    "#161616": "#ececec",
    "#212121": "#e2e2e2",
    "#2c2c2c": "#d8d9d9",
    "#373737": "#cfcfd0",
    "#434343": "#c4c5c5",
    "#4e4e4e": "#babbbc",
    "#595959": "#b0b1b3",
    "#646464": "#a6a8aa",
    "#6f6f6f": "#9c9ea0",
    "#7a7a7a": "#929597",
    "#858585": "#888b8e",
    "#909090": "#7e8185",
    "#9b9b9b": "#74787c",
    "#a6a6a6": "#6b6e72",
    "#b1b1b1": "#616568",
    "#bcbcbc": "#585b5f",
    "#c8c8c8": "#4e5154",
    "#d3d3d3": "#44474a",
    "#dedede": "#3b3e40",
    "#e9e9e9": "#323437",
    "#f4f4f4": "#292a2d",
    "#ffffff": "#202124",
    "#570f0f": "#f7c2b7",
    "#57570f": "#aeaa62",
    "#0f570f": "#82bf76",
    "#0f5757": "#79b9b8",
    "#0f0f57": "#f1dbfb",
    "#570f57": "#f7baf5",
    "#981b1b": "#f19182",
    "#98981b": "#65680c",
    "#1b981b": "#16841d",
    "#1b9898": "#0d7979",
    "#1b1b98": "#d8baf7",
    "#981b98": "#e480e2",
    "#d92626": "#eb5d53",
    "#d9d926": "#303e07",
    "#26d926": "#0a590a",
    "#26d9d9": "#094f52",
    "#2626d9": "#bd9bf4",
    "#d926d9": "#cc38cc",
    "#e46767": "#bc5153",
    "#e4e467": "#2b3606",
    "#67e467": "#084d08",
    "#67e4e4": "#084547",
    "#6767e4": "#8884ec",
    "#e467e4": "#a73aa8",
    "#f0a8a8": "#7a3f41",
    "#f0f0a8": "#262c05",
    "#a8f0a8": "#063b0c",
    "#a8f0f0": "#063637",
    "#a8a8f0": "#4e5393",
    "#f0a8f0": "#703472",
    "#0a0a0a": "#f6f6f6",
    "#e10600": "#e95038",
    "#fefefe": "#202224",
    "#f2f2ea": "#2a2a24",
    "#fdfdfb": "#222221",
    "#ffe500": "#303005",
    "#16160f": "#eeeee6",
    "#29291f": "#d8d7ca",
    "#3671c6": "#648fd8",
    "#e8002d": "#eb4a52",
    "#27f4d2": "#074231",
    "#ff8000": "#9c4411",
    "#229971": "#0e7c5d",
    "#64c4ff": "#0e547d",
    # Supplemental probe (2026-08-01): the 2026-season team colors the original Probe A missed.
    "#0093cc": "#3877a2",  # Alpine
    "#6692ff": "#446cbd",  # RB / Racing Bulls
    "#b6babd": "#4f5154",  # Haas
    "#52e252": "#224f17",  # Kick Sauber
    "#f50537": "#d74854",  # Audi
    "#e8a33d": "#6d4c1c",  # Cadillac
}


def _hex_to_rgb(hexval: str) -> tuple[int, int, int]:
    h = hexval.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(rgb: np.ndarray) -> str:
    r, g, b = (int(round(v)) for v in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(frozen=True)
class ColorTransform:
    input_rgbs: np.ndarray
    dark_rgbs: np.ndarray
    tree: cKDTree

    @classmethod
    def fit(cls, samples: dict[str, str] | None = None) -> ColorTransform:
        samples = samples if samples is not None else DARK_MODE_SAMPLES
        inputs = np.array([_hex_to_rgb(k) for k in samples], dtype=np.float64)
        darks = np.array([_hex_to_rgb(v) for v in samples.values()], dtype=np.float64)
        return cls(input_rgbs=inputs, dark_rgbs=darks, tree=cKDTree(inputs))

    def apply(self, hex_color: str) -> str:
        """The measured dark-mode result for the nearest sampled input color."""
        rgb = np.array(_hex_to_rgb(hex_color), dtype=np.float64)
        _, idx = self.tree.query(rgb)
        return _rgb_to_hex(self.dark_rgbs[idx])

    def nearest_sample_distance(self, hex_color: str) -> float:
        """Euclidean RGB distance to the nearest sample actually used to answer `apply` --
        large values mean the input color is far from anything measured, so the result is
        an extrapolation, not a real measurement."""
        rgb = np.array(_hex_to_rgb(hex_color), dtype=np.float64)
        dist, _ = self.tree.query(rgb)
        return float(dist)


def held_out_residual(samples: dict[str, str] | None = None, holdout_fraction: float = 0.2, seed: int = 0) -> float:
    """Fits on a random subset of the samples and returns the mean Euclidean RGB error on the
    rest -- states the number rather than claiming accuracy, per the emailsim plan. Not used at
    runtime by ColorTransform.apply; a reporting/diagnostic function only."""
    samples = samples if samples is not None else DARK_MODE_SAMPLES
    items = list(samples.items())
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(items))
    n_holdout = max(1, int(len(items) * holdout_fraction))
    holdout_idx, train_idx = idx[:n_holdout], idx[n_holdout:]

    train = {items[i][0]: items[i][1] for i in train_idx}
    transform = ColorTransform.fit(train)

    errors = []
    for i in holdout_idx:
        input_hex, true_dark_hex = items[i]
        predicted = transform.apply(input_hex)
        true_rgb = np.array(_hex_to_rgb(true_dark_hex), dtype=np.float64)
        pred_rgb = np.array(_hex_to_rgb(predicted), dtype=np.float64)
        errors.append(float(np.sqrt(((true_rgb - pred_rgb) ** 2).sum())))
    return sum(errors) / len(errors)
