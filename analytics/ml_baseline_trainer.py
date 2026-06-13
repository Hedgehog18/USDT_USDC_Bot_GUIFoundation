from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline


NUMERIC_FEATURES = (
    "work_position",
    "short_position",
    "long_position",
    "spread",
    "return_1",
    "return_3",
    "return_5",
    "rolling_high_low_range_5",
    "rolling_high_low_range_10",
    "distance_to_work_center",
    "distance_to_short_center",
    "distance_to_long_center",
    "candle_body",
    "candle_range",
    "upper_wick",
    "lower_wick",
)


@dataclass(frozen=True)
class MLFeatureImportance:
    name: str
    importance: float


@dataclass(frozen=True)
class MLBaselineReport:
    file_path: Path
    output_path: Path
    train_rows: int
    test_rows: int
    train_positive_rate: float
    test_positive_rate: float
    precision: float | None
    recall: float | None
    f1: float | None
    roc_auc: float | None
    pr_auc: float | None
    confusion_matrix: list[list[int]]
    top_feature_importances: list[MLFeatureImportance]
    warning: str | None = None


class MLBaselineTrainer:
    def __init__(self, output_path: str | Path = "reports/ml_baseline_report.txt") -> None:
        self.output_path = Path(output_path)

    def train(self, file_path: str | Path) -> MLBaselineReport:
        path = Path(file_path)
        rows = self._candidate_rows(path)
        if len(rows) < 4:
            report = self._empty_report(path, "Not enough candidate rows for train/test split.")
            self.export_report(report)
            return report

        split_index = max(1, int(len(rows) * 0.7))
        if split_index >= len(rows):
            split_index = len(rows) - 1

        train_rows = rows[:split_index]
        test_rows = rows[split_index:]
        y_train = [self._label(row) for row in train_rows]
        y_test = [self._label(row) for row in test_rows]
        if len(set(y_train)) < 2:
            report = self._insufficient_class_report(
                path=path,
                train_rows=train_rows,
                test_rows=test_rows,
                warning="Training split has only one target class; model was not trained.",
            )
            self.export_report(report)
            return report

        model = Pipeline([
            ("features", DictVectorizer(sparse=False)),
            (
                "model",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=42,
                ),
            ),
        ])
        model.fit([self._features(row) for row in train_rows], y_train)
        y_pred = model.predict([self._features(row) for row in test_rows])
        probabilities = model.predict_proba([self._features(row) for row in test_rows])[:, 1]
        report = MLBaselineReport(
            file_path=path,
            output_path=self.output_path,
            train_rows=len(train_rows),
            test_rows=len(test_rows),
            train_positive_rate=self._positive_rate(y_train),
            test_positive_rate=self._positive_rate(y_test),
            precision=precision_score(y_test, y_pred, zero_division=0),
            recall=recall_score(y_test, y_pred, zero_division=0),
            f1=f1_score(y_test, y_pred, zero_division=0),
            roc_auc=self._safe_roc_auc(y_test, probabilities),
            pr_auc=self._safe_pr_auc(y_test, probabilities),
            confusion_matrix=confusion_matrix(y_test, y_pred, labels=[0, 1]).tolist(),
            top_feature_importances=self._feature_importances(model),
        )
        self.export_report(report)
        return report

    def export_report(self, report: MLBaselineReport) -> Path:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.write_text(self.format_report(report), encoding="utf-8")
        return self.output_path

    def format_report(self, report: MLBaselineReport) -> str:
        lines = [
            "=== ML Baseline Training Report ===",
            f"Dataset file: {report.file_path}",
            f"Train rows: {report.train_rows}",
            f"Test rows: {report.test_rows}",
            f"Positive rate train: {report.train_positive_rate * 100:.2f}%",
            f"Positive rate test: {report.test_positive_rate * 100:.2f}%",
            f"Precision: {self._format_metric(report.precision)}",
            f"Recall: {self._format_metric(report.recall)}",
            f"F1: {self._format_metric(report.f1)}",
            f"ROC-AUC: {self._format_metric(report.roc_auc)}",
            f"PR-AUC: {self._format_metric(report.pr_auc)}",
            "Confusion matrix [actual 0/1 rows, predicted 0/1 columns]:",
        ]
        for row in report.confusion_matrix:
            lines.append(f"- {row}")
        lines.append("Top feature importances:")
        if report.top_feature_importances:
            for item in report.top_feature_importances:
                lines.append(f"- {item.name}: {item.importance:.6f}")
        else:
            lines.append("- N/A")
        if report.warning:
            lines.append(f"Warning: {report.warning}")
        lines.append(f"Output: {report.output_path}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _candidate_rows(path: Path) -> list[dict[str, str]]:
        with path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        return [row for row in rows if row.get("candidate_direction") in {"BUY_USDC", "SELL_USDC"}]

    def _empty_report(self, path: Path, warning: str) -> MLBaselineReport:
        return MLBaselineReport(
            file_path=path,
            output_path=self.output_path,
            train_rows=0,
            test_rows=0,
            train_positive_rate=0.0,
            test_positive_rate=0.0,
            precision=None,
            recall=None,
            f1=None,
            roc_auc=None,
            pr_auc=None,
            confusion_matrix=[[0, 0], [0, 0]],
            top_feature_importances=[],
            warning=warning,
        )

    def _insufficient_class_report(
        self,
        *,
        path: Path,
        train_rows: list[dict[str, str]],
        test_rows: list[dict[str, str]],
        warning: str,
    ) -> MLBaselineReport:
        return MLBaselineReport(
            file_path=path,
            output_path=self.output_path,
            train_rows=len(train_rows),
            test_rows=len(test_rows),
            train_positive_rate=self._positive_rate([self._label(row) for row in train_rows]),
            test_positive_rate=self._positive_rate([self._label(row) for row in test_rows]),
            precision=None,
            recall=None,
            f1=None,
            roc_auc=None,
            pr_auc=None,
            confusion_matrix=[[0, 0], [0, 0]],
            top_feature_importances=[],
            warning=warning,
        )

    @staticmethod
    def _features(row: dict[str, str]) -> dict[str, float | str]:
        features: dict[str, float | str] = {
            "volatility_regime": row.get("volatility_regime") or "UNKNOWN",
            "direction": row.get("candidate_direction") or "UNKNOWN",
            "hour_of_day": MLBaselineTrainer._hour(row.get("timestamp", "")),
        }
        for name in NUMERIC_FEATURES:
            features[name] = MLBaselineTrainer._float(row.get(name))
        return features

    @staticmethod
    def _label(row: dict[str, str]) -> int:
        return 1 if str(row.get("label_target_hit", "0")).strip() == "1" else 0

    @staticmethod
    def _float(value: str | None) -> float:
        try:
            return float(value or 0.0)
        except ValueError:
            return 0.0

    @staticmethod
    def _hour(value: str) -> int:
        try:
            return datetime.fromisoformat(value).hour
        except ValueError:
            return 0

    @staticmethod
    def _positive_rate(labels: list[int]) -> float:
        return sum(labels) / len(labels) if labels else 0.0

    @staticmethod
    def _safe_roc_auc(labels: list[int], probabilities) -> float | None:
        if len(set(labels)) < 2:
            return None
        return float(roc_auc_score(labels, probabilities))

    @staticmethod
    def _safe_pr_auc(labels: list[int], probabilities) -> float | None:
        if len(set(labels)) < 2:
            return None
        return float(average_precision_score(labels, probabilities))

    @staticmethod
    def _feature_importances(model: Pipeline) -> list[MLFeatureImportance]:
        vectorizer = model.named_steps["features"]
        classifier = model.named_steps["model"]
        names = vectorizer.get_feature_names_out()
        coefficients = classifier.coef_[0]
        pairs = [
            MLFeatureImportance(name=name, importance=abs(float(value)))
            for name, value in zip(names, coefficients)
        ]
        return sorted(pairs, key=lambda item: item.importance, reverse=True)[:10]

    @staticmethod
    def _format_metric(value: float | None) -> str:
        return "N/A" if value is None else f"{value:.4f}"
