import json
import numpy as np
from pathlib import Path
from sklearn.metrics.pairwise import cosine_similarity


RIASEC_DIMENSIONS = [
    "creates_expresses",
    "organizes_systems",
    "investigates_why",
    "builds_tinkers",
    "works_with_people",
    "leads_persuades",
]


ROOT_DIR = Path(__file__).resolve().parent.parent
CAREER_GRAPH_PATH = ROOT_DIR / "Outputs" / "career_graph.json"


def load_career_graph():
    """Load the occupation graph."""

    with open(CAREER_GRAPH_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def get_occupation_vector(occupation):
    """Get the six-dimensional RIASEC vector."""

    return np.array(
        [
            occupation["riasec"][dimension]
            for dimension in RIASEC_DIMENSIONS
        ],
        dtype=float,
    )


def find_occupation(career_graph, occupation_id):
    """Find an occupation by its O*NET-SOC ID."""

    for occupation in career_graph:
        if occupation["id"] == occupation_id:
            return occupation

    raise ValueError(f"Occupation not found: {occupation_id}")


def explain_match(student_vector, occupation_id):
    """
    Calculate SHAP contribution scores for the six RIASEC
    dimensions for a specific occupation match.
    """

    # Imported here, not at module load: shap (with numba) costs about
    # 65 MB the moment it's imported, and this endpoint is the only
    # thing that uses it - the 512 MB host shouldn't pay that at
    # startup for every request that never asks for an explanation.
    import shap

    career_graph = load_career_graph()

    occupation = find_occupation(
        career_graph,
        occupation_id,
    )

    occupation_vector = get_occupation_vector(occupation)

    student_vector = np.asarray(
        student_vector,
        dtype=float,
    )

    # The function SHAP explains:
    # cosine similarity between the student and occupation.
    def matching_function(X):

        X = np.asarray(X, dtype=float)

        return np.array([
            cosine_similarity(
                row.reshape(1, -1),
                occupation_vector.reshape(1, -1),
            )[0][0]
            for row in X
        ])

    # Background data for KernelExplainer.
    background = np.array([
        get_occupation_vector(occupation)
        for occupation in career_graph[:10]
    ])

    explainer = shap.KernelExplainer(
        matching_function,
        background,
    )

    shap_values = explainer.shap_values(
        student_vector.reshape(1, -1),
        nsamples=100,
    )

    # SHAP versions can return different shapes.
    shap_values = np.asarray(shap_values)

    if shap_values.ndim == 3:
        shap_values = shap_values[0][0]
    elif shap_values.ndim == 2:
        shap_values = shap_values[0]

    contributions = {
        dimension: float(value)
        for dimension, value in zip(
            RIASEC_DIMENSIONS,
            shap_values,
        )
    }

    similarity = float(
        matching_function(
            student_vector.reshape(1, -1)
        )[0]
    )

    return {
        "occupation_id": occupation["id"],
        "occupation": occupation["title"],
        "similarity": similarity,
        "contributions": contributions,
    }