import gzip
import json
from pathlib import Path

import pytest
from probability_model import count_over
import streamlit_app as app


ROOT = Path(__file__).resolve().parents[1]


def _write_study(root, *, holdout_opened=False, predictions=None):
    research = root / "research"
    research.mkdir(parents=True)
    if predictions is None:
        mean = 2.5
        predictions = {
            "development": [
                {
                    "season": "20232024",
                    "player": "Visible Player",
                    "player_id": 1,
                    "game_date": "2023-11-01",
                    "game_id": 10,
                    "position": "F",
                    "volume_tier": "high",
                    "history_games": 12,
                    "prior_games": 40,
                    "actual": 3,
                    "means": {
                        "blend20_nb20": mean,
                        "season_poisson": 2.4,
                        "recent10_poisson": 2.2,
                    },
                    "probabilities": {
                        "blend20_nb20": [count_over(line, mean, 20) for line in (1.5, 2.5, 3.5)],
                    },
                },
                {
                    "season": "20252026",
                    "player": "Holdout Player",
                    "player_id": 99,
                    "game_date": "2025-10-10",
                    "game_id": 99,
                    "position": "F",
                    "volume_tier": "high",
                    "history_games": 12,
                    "prior_games": 40,
                    "actual": 9,
                    "means": {"blend20_nb20": 9},
                    "probabilities": {"blend20_nb20": [0.9, 0.8, 0.7]},
                },
            ],
            "validation": [],
            "holdout": [{"season": "20252026", "player": "Sealed Split", "means": {}, "probabilities": {}}],
        }
    report = {"holdout_opened": holdout_opened, "holdout_loaded": False, "folds": {}}
    selected = {"name": "blend20_nb20", "spec": {"kind": "blend", "strength": 20, "dispersion": 20}}
    protocol = {
        "development_season": "20232024",
        "validation_season": "20242025",
        "reserved_holdout": "20252026",
        "prior_window": 30,
        "min_prior_games": 20,
        "frozen_at": "2026-10-02T00:00:00+00:00",
        "limitations": ["No market prices."],
    }
    (research / "predictions.json.gz").write_bytes(gzip.compress(json.dumps(predictions).encode()))
    (research / "report.json.gz").write_bytes(gzip.compress(json.dumps(report).encode()))
    (research / "selected_model.json").write_text(json.dumps(selected))
    (research / "protocol.json").write_text(json.dumps(protocol))


def test_module_imports_and_repo_study_stays_on_public_seasons():
    data = app.load_showcase(ROOT)
    seasons = {row["season"] for row in data["records"]}
    assert seasons == {"20232024", "20242025"}
    assert data["holdout_rows_omitted"] == 0
    assert data["report"]["holdout_opened"] is False
    assert data["report"]["holdout_loaded"] is False
    assert data["model_name"] == "blend20_nb20"
    assert data["dispersion"] == 20
    assert len(data["records"]) == 1449 + 1343


def test_distribution_matches_stored_lines_for_a_real_game():
    data = app.load_showcase(ROOT)
    row = next(
        item for item in data["records"]
        if item["player"] == "Nathan MacKinnon"
        and item["season"] == "20242025"
        and item["game_date"] == "2025-04-08"
    )
    mean = row["means"][data["model_name"]]
    lines = app.line_probabilities(mean, data["dispersion"])
    assert [item["line"] for item in lines] == [1.5, 2.5, 3.5, 4.5]
    stored = row["probabilities"][data["model_name"]]
    for got, expected in zip(lines, stored):
        assert got["over"] == pytest.approx(expected, abs=1e-9)
        assert got["over"] + got["under"] == pytest.approx(1)
    assert lines[3]["over"] < lines[2]["over"]
    dist = app.shot_pmf(mean, data["dispersion"], actual=row["actual"])
    assert sum(item["probability"] for item in dist) == pytest.approx(1, abs=1e-8)
    assert all(item["probability"] >= 0 for item in dist)
    assert sum(item["bar"] == "Recorded result" for item in dist) == 1


def test_holdout_rows_are_omitted_and_an_opened_holdout_is_refused(tmp_path):
    _write_study(tmp_path)
    data = app.load_showcase(tmp_path)
    assert [row["player"] for row in data["records"]] == ["Visible Player"]
    assert data["holdout_rows_omitted"] == 2
    assert "20252026" not in {row["season"] for row in data["records"]}
    _write_study(tmp_path / "opened", holdout_opened=True)
    with pytest.raises(ValueError, match="sealed holdout"):
        app.load_showcase(tmp_path / "opened")


def test_about_copy_keeps_the_result_unproven():
    data = app.load_showcase(ROOT)
    text = "\n".join([
        app.model_blurb(data["selected"], data["protocol"]),
        app.validation_claim(data["report"], data["model_name"]),
        app.holdout_sentence(data["protocol"]),
    ])
    assert "blend20_nb20" in text
    assert "sealed holdout" in text
    assert "2025–26" in text
    assert "includes zero" in text
    assert "betting edge" in text


def test_app_script_renders(tmp_path):
    pytest.importorskip("streamlit.testing.v1")
    from streamlit.testing.v1 import AppTest

    page = AppTest.from_file(ROOT / "streamlit_app.py", default_timeout=60).run()
    assert not page.exception, page.exception
    assert page.selectbox
    assert page.metric
    rendered = " ".join(getattr(item, "value", "") for item in list(page.markdown) + list(page.subheader))
    assert "Nathan MacKinnon" in rendered
