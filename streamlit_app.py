"""Display-only Streamlit showcase for frozen shots-on-goal research.

Reads the committed 2023–24 development and 2024–25 validation artifacts.
Does not train, tune, fetch, or display the sealed 2025–26 holdout.
"""
import gzip
import json
from pathlib import Path

import altair as alt
import streamlit as st

from probability_model import count_over

HOLDOUT_SEASON = "20252026"
COMMON_LINES = (1.5, 2.5, 3.5, 4.5)
DISTRIBUTION_TAIL = 12
DEFAULT_PLAYER = "Nathan MacKinnon"

SEASON_LABELS = {
    "20232024": "2023–24 development",
    "20242025": "2024–25 validation",
}
POSITION_LABELS = {"F": "Forward", "D": "Defense"}
MODEL_LABELS = {
    "blend20_nb20": "Selected blend + negative binomial",
    "season_poisson": "Season-average Poisson",
    "recent10_poisson": "Last-ten Poisson",
    "legacy_full": "Legacy shots.py engine",
}
COMPARISON_MODELS = ("season_poisson", "recent10_poisson", "legacy_full")
SAMPLE_LABELS = (
    ("all", "All scored games"),
    ("early", "1–9 current-season games"),
    ("established", "10 or more current-season games"),
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def allowed_seasons(protocol):
    """Development and validation seasons only. The reserved holdout is excluded."""
    holdout = str(protocol.get("reserved_holdout") or HOLDOUT_SEASON)
    seasons = []
    for key in ("development_season", "validation_season"):
        season = str(protocol.get(key) or "")
        if season and season not in (holdout, HOLDOUT_SEASON):
            seasons.append(season)
    return tuple(seasons)


def public_records(predictions, allowed):
    """Return showcase rows, counting anything from the sealed holdout as omitted."""
    if not isinstance(predictions, dict):
        raise ValueError("Predictions file must be a JSON object")
    allowed = {str(season) for season in allowed}
    rows = []
    omitted = 0
    for split in ("development", "validation"):
        items = predictions.get(split) or []
        if not isinstance(items, list):
            raise ValueError(f"{split} predictions must be a list")
        for row in items:
            season = str(row.get("season", ""))
            if season == HOLDOUT_SEASON or season not in allowed:
                omitted += 1
                continue
            if "means" not in row or "probabilities" not in row:
                continue
            rows.append({**row, "split": split})
    holdout_rows = predictions.get("holdout")
    if isinstance(holdout_rows, list):
        omitted += len(holdout_rows)
    return rows, omitted


def load_showcase(root=None):
    """Load committed study artifacts. Never opens raw logs or the dataset dump."""
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    research = root / "research"
    try:
        predictions = read_gz(research / "predictions.json.gz")
        report = read_gz(research / "report.json.gz")
        selected = read_json(research / "selected_model.json")
        protocol = read_json(research / "protocol.json")
    except FileNotFoundError as exc:
        missing = Path(exc.filename).name if exc.filename else "study file"
        raise FileNotFoundError(
            f"Missing {missing}. This page only reads the committed research study."
        ) from exc
    if report.get("holdout_opened") or report.get("holdout_loaded"):
        raise ValueError(
            "This study opened the sealed holdout. The showcase will not display it."
        )
    seasons = allowed_seasons(protocol)
    records, omitted = public_records(predictions, seasons)
    spec = selected.get("spec") or {}
    return {
        "records": records,
        "report": report,
        "selected": selected,
        "protocol": protocol,
        "model_name": selected["name"],
        "dispersion": spec.get("dispersion"),
        "holdout_rows_omitted": omitted,
        "seasons": seasons,
    }


def season_label(season):
    return SEASON_LABELS.get(str(season), str(season))


def season_choices(records):
    present = {str(row["season"]) for row in records}
    ordered = [season for season in SEASON_LABELS if season in present]
    ordered += sorted(present - set(ordered))
    return ordered


def shot_pmf(mean, dispersion, actual=None, tail=DISTRIBUTION_TAIL):
    """Probability mass from the frozen count model, plus one tail bucket."""
    upper = tail
    if actual is not None:
        upper = max(upper, min(int(actual) + 1, 30))
    rows = []
    for shots in range(upper):
        probability = _pmf_at(mean, dispersion, shots)
        rows.append({
            "shots": str(shots),
            "probability": probability,
            "bar": "Recorded result" if actual == shots else "Model",
        })
    tail_probability = count_over(upper - 0.5, mean, dispersion) if upper else 1.0
    rows.append({
        "shots": f"{upper}+",
        "probability": max(0.0, tail_probability),
        "bar": "Recorded result" if actual is not None and actual >= upper else "Model",
    })
    return rows


def _pmf_at(mean, dispersion, shots):
    at_least = 1.0 if shots == 0 else count_over(shots - 0.5, mean, dispersion)
    after = count_over(shots + 0.5, mean, dispersion)
    return max(0.0, at_least - after)


def line_probabilities(mean, dispersion, lines=COMMON_LINES):
    """Over/under probabilities. Half-point lines have no push."""
    rows = []
    for line in lines:
        over = count_over(float(line), mean, dispersion)
        rows.append({"line": float(line), "over": over, "under": 1.0 - over})
    return rows


def model_blurb(selected, protocol):
    spec = selected.get("spec") or {}
    name = selected.get("name", "the selected model")
    window = protocol.get("prior_window", 30)
    strength = spec.get("strength")
    dispersion = spec.get("dispersion")
    if spec.get("kind") == "blend" and strength and dispersion:
        return (
            f"{name} shrinks a player's current-season shots average toward the last "
            f"{window} appearances from the prior season. The prior season is worth "
            f"{strength} games in that average. A negative-binomial distribution with "
            f"dispersion {dispersion} turns the average into a full shot distribution."
        )
    return (
        f"The frozen model is {name}. Over/under chances come from the count "
        "distribution stored with that choice."
    )


def validation_claim(report, model_name):
    fold = report["folds"]["validation"]
    selected = fold["groups"]["all"][model_name]
    baseline = fold["groups"]["all"]["season_poisson"]
    interval = fold["paired_comparisons"]["all"]["season_poisson"]
    lower, upper = interval["lower"], interval["upper"]
    sentence = (
        f"On the 2024–25 validation sample ({selected['games']:,} player games), "
        f"the selected Brier score is {selected['brier']:.6f} versus {baseline['brier']:.6f} "
        f"for a season-average Poisson baseline. The paired difference is "
        f"{interval['difference']:.6f}, with a descriptive 95 percent interval "
        f"from {lower:.6f} to {upper:.6f}."
    )
    if lower <= 0 <= upper:
        sentence += (
            " That interval includes zero, so this showcase does not treat the model "
            "as a proven improvement or a betting edge."
        )
    else:
        sentence += (
            " That interval excludes zero on this fixed cohort. It is still a "
            "descriptive interval, not evidence of a betting edge."
        )
    return sentence


def holdout_sentence(protocol):
    reserved = str(protocol.get("reserved_holdout") or HOLDOUT_SEASON)
    label = "2025–26" if reserved == HOLDOUT_SEASON else reserved
    return (
        f"The {label} season is a sealed holdout. This app does not read, score, or display it."
    )


def pct(value):
    return f"{value * 100:.1f}%"


def comparison_rows(report, fold, model_name):
    groups = report["folds"][fold]["groups"]["all"]
    names = [model_name] + [name for name in COMPARISON_MODELS if name != model_name and name in groups]
    rows = []
    for name in names:
        score = groups[name]
        rows.append({
            "Model": MODEL_LABELS.get(name, name),
            "Role": "Selected" if name == model_name else "Comparison",
            "Brier": f"{score['brier']:.6f}",
            "MAE": f"{score['mae']:.3f}",
            "RMSE": f"{score['rmse']:.3f}",
        })
    return rows


def sample_rows(report, fold, model_name):
    groups = report["folds"][fold]["groups"]
    rows = []
    for key, label in SAMPLE_LABELS:
        if key not in groups or model_name not in groups[key]:
            continue
        selected = groups[key][model_name]
        baseline = groups[key].get("season_poisson") or {}
        rows.append({
            "Sample": label,
            "Games": selected["games"],
            "Selected Brier": f"{selected['brier']:.6f}",
            "Season baseline": f"{baseline['brier']:.6f}" if baseline.get("brier") is not None else "—",
        })
    return rows


def interval_rows(report, fold):
    pairs = report["folds"][fold]["paired_comparisons"]["all"]
    rows = []
    for name, label in ((key, MODEL_LABELS.get(key, key)) for key in COMPARISON_MODELS):
        item = pairs.get(name)
        if not item or item.get("difference") is None:
            continue
        rows.append({
            "Versus": label,
            "Selected minus other": f"{item['difference']:.6f}",
            "Lower": f"{item['lower']:.6f}",
            "Upper": f"{item['upper']:.6f}",
        })
    return rows


def calibration_table(bins):
    rows = []
    for bucket in bins:
        lower = bucket["lower"]
        rows.append({
            "Predicted bin": f"{lower:.1f}–{lower + 0.1:.1f}",
            "Outcomes": bucket["count"],
            "Predicted": pct(bucket["predicted"]),
            "Observed": pct(bucket["observed"]),
        })
    return rows


def distribution_chart(rows):
    return (
        alt.Chart(alt.Data(values=rows))
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("shots:O", sort=None, title="Shots on goal"),
            y=alt.Y("probability:Q", title="Probability", axis=alt.Axis(format="%")),
            color=alt.Color(
                "bar:N",
                title=None,
                scale=alt.Scale(
                    domain=["Model", "Recorded result"],
                    range=["#1f4e79", "#c46b3a"],
                ),
                legend=alt.Legend(orient="top"),
            ),
            tooltip=[
                alt.Tooltip("shots:O", title="Shots"),
                alt.Tooltip("probability:Q", title="Probability", format=".1%"),
            ],
        )
        .properties(height=280)
        .configure(background="transparent")
        .configure_view(strokeWidth=0)
    )


def calibration_chart(bins):
    points = [{
        "predicted": bucket["predicted"],
        "observed": bucket["observed"],
        "count": bucket["count"],
        "bin": f"{bucket['lower']:.1f}–{bucket['lower'] + 0.1:.1f}",
    } for bucket in bins]
    x = alt.X("predicted:Q", title="Predicted rate", scale=alt.Scale(domain=[0, 1]))
    y = alt.Y("observed:Q", title="Observed rate", scale=alt.Scale(domain=[0, 1]))
    guide = (
        alt.Chart(alt.Data(values=[{"predicted": 0, "observed": 0}, {"predicted": 1, "observed": 1}]))
        .mark_line(strokeDash=[6, 4], color="#1f4e79")
        .encode(x=x, y=y)
    )
    dots = (
        alt.Chart(alt.Data(values=points))
        .mark_circle(color="#c46b3a", opacity=0.9)
        .encode(
            x=x,
            y=y,
            size=alt.Size("count:Q", title="Outcomes", scale=alt.Scale(range=[50, 420])),
            tooltip=[
                alt.Tooltip("bin:N", title="Bin"),
                alt.Tooltip("predicted:Q", title="Predicted", format=".1%"),
                alt.Tooltip("observed:Q", title="Observed", format=".1%"),
                alt.Tooltip("count:Q", title="Outcomes"),
            ],
        )
    )
    return (guide + dots).properties(height=320).configure(background="transparent").configure_view(strokeWidth=0)


def _index(options, preferred):
    return options.index(preferred) if preferred in options else 0


def _established_index(games):
    return max(range(len(games)), key=lambda i: (games[i]["history_games"], games[i]["game_date"]))


def _mean(row, model_name):
    return float(row["means"][model_name])


def game_label(row, model_name):
    return (
        f"{row['game_date']} · {_mean(row, model_name):.2f} expected · "
        f"{row['history_games']} games already played"
    )


def slate_table(rows, model_name, dispersion):
    table = []
    for row in sorted(rows, key=lambda item: _mean(item, model_name), reverse=True):
        mean = _mean(row, model_name)
        table.append({
            "Player": row["player"],
            "Position": POSITION_LABELS.get(row["position"], row["position"]),
            "Expected shots": f"{mean:.2f}",
            "Over 2.5": pct(count_over(2.5, mean, dispersion)),
            "Actual shots": row["actual"],
        })
    return table


def inject_css():
    st.html(
        """
        <style>
        .block-container { padding-top: 1.4rem; max-width: 1080px; }
        .banner {
          background: #0f2744;
          color: #f6f3ee;
          padding: 1.25rem 1.4rem 1.15rem;
          border-radius: 14px;
          margin-bottom: 0.8rem;
        }
        .banner h1 {
          margin: 0;
          font-size: 1.75rem;
          letter-spacing: -0.02em;
          font-weight: 650;
        }
        .banner p { margin: 0.45rem 0 0; color: #d7e0ea; line-height: 1.45; }
        div[data-testid="stMetric"] {
          background: #fffdf8;
          border: 1px solid #e6dfd2;
          border-radius: 12px;
          padding: 0.45rem 0.75rem 0.15rem;
        }
        </style>
        """
    )


def render_filters(bundle):
    records = bundle["records"]
    model_name = bundle["model_name"]
    seasons = season_choices(records)
    filters, mode_col = st.columns([1.3, 1.5])
    season = filters.selectbox(
        "Season",
        seasons,
        index=_index(seasons, "20242025"),
        format_func=season_label,
        key="season",
    )
    mode = mode_col.radio("Browse by", ["Player", "Date"], horizontal=True, key="browse_by")
    subset = [row for row in records if str(row["season"]) == str(season)]
    left, right = st.columns(2)
    if mode == "Player":
        players = sorted({row["player"] for row in subset})
        player = left.selectbox(
            "Player",
            players,
            index=_index(players, DEFAULT_PLAYER),
            key=f"player-{season}",
        )
        games = sorted(
            (row for row in subset if row["player"] == player),
            key=lambda row: (row["game_date"], row.get("game_id", 0)),
        )
        if not games:
            return None, None
        choice = right.selectbox(
            "Game",
            range(len(games)),
            format_func=lambda i, games=games: game_label(games[i], model_name),
            index=_established_index(games),
            key=f"game-{season}-{player}",
        )
        return games[choice], None
    dates = sorted({row["game_date"] for row in subset})
    if not dates:
        return None, None
    day = left.selectbox("Date", dates, index=len(dates) - 1, key=f"date-{season}")
    slate = sorted(
        (row for row in subset if row["game_date"] == day),
        key=lambda row: _mean(row, model_name),
        reverse=True,
    )
    if not slate:
        return None, None
    choice = right.selectbox(
        "Player that day",
        range(len(slate)),
        format_func=lambda i, slate=slate: f"{slate[i]['player']} · {_mean(slate[i], model_name):.2f} expected",
        key=f"slate-{season}-{day}",
    )
    return slate[choice], slate


def render_game(bundle, row, slate):
    model_name = bundle["model_name"]
    dispersion = bundle["dispersion"]
    mean = _mean(row, model_name)
    lines = line_probabilities(mean, dispersion)
    position = POSITION_LABELS.get(row["position"], row["position"])
    st.subheader(f"{row['player']} on {row['game_date']}")
    st.caption(
        f"{season_label(row['season'])} · {position} · {row['volume_tier']} volume · "
        f"{row['history_games']} current-season games already played · "
        f"{row['prior_games']} prior-season games on file"
    )
    if row["history_games"] < 10:
        st.info(
            f"Early-season sample: only {row['history_games']} current-season "
            "games before this one, so the prior season carries more of the average."
        )
    expected, season_avg, recent, actual = st.columns(4)
    expected.metric("Expected shots", f"{mean:.2f}")
    season_value = row["means"].get("season_poisson")
    recent_value = row["means"].get("recent10_poisson")
    season_avg.metric("Season average", "—" if season_value is None else f"{season_value:.2f}")
    recent.metric("Last ten average", "—" if recent_value is None else f"{recent_value:.2f}")
    actual.metric("Actual shots", str(row["actual"]))
    st.caption(
        "Actual shots are the recorded result. They were not an input. "
        "The selected model uses shot history only."
    )
    st.altair_chart(distribution_chart(shot_pmf(mean, dispersion, actual=int(row["actual"]))), width="stretch")
    columns = st.columns(4)
    for column, item in zip(columns, lines):
        column.metric(f"Over {item['line']}", pct(item["over"]))
        column.caption(f"Under {pct(item['under'])}")
    st.caption(
        "Over 1.5 means 2 or more shots. The same reading applies at 2.5, 3.5, and 4.5. "
        "These are model probabilities, not sportsbook prices. The 1.5, 2.5, and 3.5 lines "
        "match the stored study (2+, 3+, and 4+). Over 4.5 uses that same frozen distribution."
    )
    if slate:
        st.markdown("**Study players who played that day**")
        st.dataframe(slate_table(slate, model_name, dispersion), hide_index=True, width="stretch")


def render_about(bundle):
    protocol = bundle["protocol"]
    frozen = str(protocol.get("frozen_at") or "")[:10]
    st.markdown(model_blurb(bundle["selected"], protocol))
    st.markdown(validation_claim(bundle["report"], bundle["model_name"]))
    st.markdown(holdout_sentence(protocol))
    minimum_prior = protocol.get("min_prior_games", 20)
    st.markdown(
        "Games in this page already had at least one current-season appearance and "
        f"{minimum_prior} prior-season appearances. The 24-player cohort was fixed from "
        "2022–23 shot rates, with forwards and defensemen in three volume tiers. "
        "Power-play time, injuries, and confirmed deployment are not inputs."
    )
    limitations = protocol.get("limitations") or []
    if limitations:
        st.markdown("**Limits**")
        for item in limitations:
            st.markdown(f"- {item}")
    if frozen:
        st.caption(
            f"Study frozen {frozen}. The model was chosen on development Brier only, "
            "before any validation game was scored."
        )


def render_backtest(bundle):
    report = bundle["report"]
    model_name = bundle["model_name"]
    folds = report.get("folds") or {}
    if "validation" not in folds:
        st.info("The committed report has no validation backtest to summarize.")
        return
    options = [name for name in ("validation", "development") if name in folds]
    fold = st.radio(
        "Sample",
        options,
        format_func=lambda name: "2024–25 validation" if name == "validation" else "2023–24 development",
        horizontal=True,
        key="backtest_sample",
    )
    if fold == "development":
        st.info("Development scores were used to choose the model, so they are optimistic.")
    score = folds[fold]["groups"]["all"][model_name]
    games, players, brier, mae = st.columns(4)
    games.metric("Player games", f"{score['games']:,}")
    players.metric("Players", f"{score['players']}")
    brier.metric("Brier", f"{score['brier']:.6f}")
    mae.metric("MAE", f"{score['mae']:.3f}")
    st.caption(
        f"RMSE {score['rmse']:.3f}. Brier averages the 2+, 3+, and 4+ lines on the same games. "
        "Lower is better."
    )
    st.markdown("**Same games, other models**")
    st.dataframe(comparison_rows(report, fold, model_name), hide_index=True, width="stretch")
    st.markdown("**Early season and established players**")
    st.dataframe(sample_rows(report, fold, model_name), hide_index=True, width="stretch")
    st.markdown("**Paired comparison**")
    st.dataframe(interval_rows(report, fold), hide_index=True, width="stretch")
    st.caption(
        "Difference is the selected model minus the other model. A negative number favors "
        "the selected model. Intervals are the study's descriptive 95 percent player-cluster "
        "bootstraps."
    )
    st.markdown("**Calibration**")
    bins = score.get("calibration") or []
    if bins:
        st.altair_chart(calibration_chart(bins), width="stretch")
        st.dataframe(calibration_table(bins), hide_index=True, width="stretch")
    st.caption(
        "Each player game contributes three outcomes: 2 or more, 3 or more, and 4 or more shots. "
        "Points closer to the diagonal are better calibrated."
    )


def main():
    st.set_page_config(page_title="NHL shots on goal", page_icon="🏒", layout="wide")
    inject_css()
    st.html(
        """
        <div class="banner">
          <h1>NHL shots on goal</h1>
          <p>Pick a player or a date and see the frozen model's shot distribution,
          plus the chance of clearing 1.5, 2.5, 3.5, and 4.5. Research showcase only.</p>
        </div>
        """
    )
    st.caption(
        "2025–26 is a sealed holdout and is not loaded. "
        "Probabilities are not sportsbook prices and not a betting recommendation."
    )
    try:
        bundle = cached_showcase()
    except ValueError as exc:
        st.error(str(exc))
        return
    except Exception as exc:
        st.error("The committed study files could not be read.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return
    if bundle["holdout_rows_omitted"]:
        st.warning("Sealed holdout rows were in the study file and were left off this page.")
    if not bundle["records"]:
        st.warning("No development or validation games were available to show.")
        return
    row, slate = render_filters(bundle)
    game_tab, about_tab, backtest_tab = st.tabs(["This game", "About the model", "Backtest"])
    with game_tab:
        if row is None:
            st.info("No game matches those filters.")
        else:
            render_game(bundle, row, slate)
    with about_tab:
        render_about(bundle)
    with backtest_tab:
        render_backtest(bundle)


@st.cache_data(show_spinner="Reading saved predictions…")
def cached_showcase():
    return load_showcase()


if __name__ == "__main__":
    main()
