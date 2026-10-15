"""Deterministic synthetic topology examples, never real XRT ground truth."""

import cv2
import numpy as np

SYNTHETIC_CASES = (
    "straight",
    "curve",
    "y",
    "t",
    "cross",
    "separated",
    "parallel",
    "short_branch",
    "boundary",
    "weak",
    "point_noise",
    "empty",
)


def synthetic_sample(name, *, polarity="bright", dtype="uint8", rgb=False):
    if name not in SYNTHETIC_CASES or polarity not in ("bright", "dark"):
        raise ValueError("Unknown synthetic case/polarity")
    image = np.full((160, 160), 120, np.uint8)
    ink = 220 if polarity == "bright" else 20

    def line(a, b, width=5):
        cv2.line(image, a, b, ink, width)

    if name == "straight":
        line((20, 80), (140, 80))
    elif name == "curve":
        cv2.ellipse(image, (80, 90), (60, 35), 0, 190, 350, ink, 5)
    elif name == "y":
        for p in ((35, 25), (125, 25), (80, 140)):
            line((80, 80), p)
    elif name == "t":
        line((20, 40), (140, 40))
        line((80, 40), (80, 140))
    elif name == "cross":
        line((20, 20), (140, 140))
        line((20, 140), (140, 20))
    elif name == "separated":
        line((20, 40), (70, 40))
        line((90, 110), (140, 110))
    elif name == "parallel":
        line((20, 65), (140, 65))
        line((20, 85), (140, 85))
    elif name == "short_branch":
        line((20, 90), (140, 90))
        line((80, 90), (80, 80), 3)
    elif name == "boundary":
        line((0, 80), (140, 80))
    elif name == "weak":
        cv2.line(image, (20, 80), (140, 80), 130 if polarity == "bright" else 110, 5)
    elif name == "point_noise":
        for x, y in (
            (20, 20),
            (60, 20),
            (100, 20),
            (140, 20),
            (20, 60),
            (60, 60),
            (100, 60),
            (140, 60),
            (20, 100),
            (60, 100),
            (100, 100),
            (140, 100),
            (20, 140),
            (60, 140),
            (100, 140),
            (140, 140),
        ):
            cv2.circle(image, (x, y), 2, ink, -1)
    if dtype == "uint16":
        image = image.astype(np.uint16) * 257
    elif dtype != "uint8":
        raise ValueError("Synthetic dtype must be uint8/uint16")
    if rgb:
        image = np.repeat(image[:, :, None], 3, axis=2)
    return image
