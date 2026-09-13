"""Marathon bib-number recognition: dataset, benchmark harness and pipeline."""

from .dataset import Box, Dataset, Sample
from .metrics import Prediction, ScoreBoard, levenshtein

__all__ = ["Box", "Dataset", "Sample", "Prediction", "ScoreBoard", "levenshtein"]
__version__ = "0.1.0"
