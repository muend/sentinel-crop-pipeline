"""SCL-based cloud/shadow masking.

SCL classes (S2 L2A): 0 nodata, 1 saturated/defective, 2 dark area, 3 cloud
shadow, 4 vegetation, 5 not vegetated, 6 water, 7 unclassified, 8 cloud medium
prob., 9 cloud high prob., 10 thin cirrus, 11 snow.

Default invalid set keeps dark areas (2) and unclassified (7); adjust via
scl_filter.invalid_classes in config.
"""

import numpy as np

DEFAULT_INVALID_CLASSES = (0, 1, 3, 8, 9, 10, 11)


def valid_mask(scl: np.ndarray,
               invalid_classes=DEFAULT_INVALID_CLASSES) -> np.ndarray:
    """Boolean mask: True where the pixel is usable."""
    return ~np.isin(scl, list(invalid_classes))


def invalid_fraction(scl: np.ndarray,
                     invalid_classes=DEFAULT_INVALID_CLASSES) -> float:
    if scl.size == 0:
        return 1.0
    return float(np.isin(scl, list(invalid_classes)).mean())
