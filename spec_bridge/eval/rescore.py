"""Re-score saved predictions with the current scorer (CP-S3 R4).

Run: uv run python -m spec_bridge.eval.rescore var/eval/<run_id> [...]
Writes var/eval/<run_id>/rescored-<scorer id>.json next to the original metrics.json,
which is never overwritten. The scorer id hashes the evaluation code and the answer set.
"""

import hashlib
import json
import sys
from pathlib import Path

from spec_bridge.dedup import matcher
from spec_bridge.eval import dedup_scoring, handwritten, locations, scoring, validation_scoring
from spec_bridge.eval.dedup_scoring import evaluate_dedup
from spec_bridge.eval.scoring import Prediction, score_split
from spec_bridge.eval.validation_scoring import validate_predictions
from spec_bridge.normalize.dictionary import ROOT, split_answers
from spec_bridge.ontology.loader import load_ontology
from spec_bridge.validate import findings, validator

ANSWER_FILES = (ROOT / "data/synth/dataset-manifest.yaml", ROOT / "data/synth/SHA256SUMS")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluation_hashes() -> dict[str, str]:
    """What decides a score: evaluation modules and the frozen answer set."""
    evaluated = [scoring, locations]
    evaluated += [validation_scoring, validator, findings]  # W4-4: G3
    evaluated += [dedup_scoring, matcher]  # W4-5: G4
    modules = {m.__name__: _sha256(Path(str(m.__file__))) for m in evaluated}
    return modules | {path.name: _sha256(path) for path in ANSWER_FILES}


def scorer_id() -> str:
    text = json.dumps(evaluation_hashes(), sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def rescore(run_dir: Path) -> Path:
    predictions = {}
    for path in sorted((run_dir / "predictions").glob("*.json")):
        prediction = Prediction.model_validate(json.loads(path.read_text())["prediction"])
        predictions[prediction.document_id] = prediction
    run = run_dir / "run.json"
    split = json.loads(run.read_text()).get("split", "dev") if run.exists() else "dev"
    answers = handwritten.answers() if split == "handwritten" else split_answers(split)
    scores, metrics = score_split(answers, predictions)  # no file -> failure, kept
    onto = load_ontology(ROOT / "ontology/ontology.yaml")
    labelled = split != "handwritten"  # v2 labelled no issues or pairs: no G3/G4 there
    validation_scores, validation = validate_predictions(onto, answers, predictions)
    out = run_dir / f"rescored-{scorer_id()}.json"
    record = {
        "scorer_id": scorer_id(),
        "evaluation": evaluation_hashes(),
        "metrics": metrics.model_dump(),
        "scores": [s.model_dump() for s in scores],
        "validation": validation.model_dump() if labelled else None,
        "validation_scores": [s.model_dump() for s in validation_scores] if labelled else [],
        "split": split,
        "dedup": evaluate_dedup(answers, predictions, split).model_dump() if labelled else None,
    }
    out.write_text(json.dumps(record, indent=2) + "\n")
    return out


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        path = rescore(Path(arg))
        metrics = json.loads(path.read_text())["metrics"]
        micro = metrics["facts_micro"]
        print(
            f"{Path(arg).name}: F1 {micro['f1']:.3f} (P {micro['precision']:.3f}, "
            f"R {micro['recall']:.3f}) macro-attr {metrics['facts_macro_f1_attribute']:.3f} "
            f"top1 {metrics['class_top1']:.3f} occ-precision {metrics['occurrence_precision']:.3f}"
            f" -> {path.name}"
        )
