import hashlib
import random
from pathlib import Path

import pandas as pd
import streamlit as st

APP_TITLE = "Buzzword Bingo"
WORDS_CSV = Path(__file__).parent / "buzzwords.csv"

BOARD_SIZE = 5
FREE_SPACE = "FREE SPACE"
DEFAULT_SEED = "team-all-hands"

TOTAL_CELLS = BOARD_SIZE * BOARD_SIZE
FREE_INDEX = TOTAL_CELLS // 2

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎯",
    layout="centered",
)


# -----------------------------
# Query param helpers
# -----------------------------

def get_query_value(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
    except Exception:
        params = st.experimental_get_query_params()
        values = params.get(name, [default])
        value = values[0] if values else default

    if isinstance(value, list):
        value = value[0] if value else default

    return str(value).strip()


def selected_to_query_param(selected: set[int]) -> str:
    return ",".join(
        str(index)
        for index in sorted(selected)
        if index != FREE_INDEX
    )


def update_query_params(seed: str, selected: set[int]) -> None:
    selected_text = selected_to_query_param(selected)

    try:
        st.query_params.clear()
        st.query_params["seed"] = seed

        if selected_text:
            st.query_params["selected"] = selected_text

    except Exception:
        params = {"seed": seed}

        if selected_text:
            params["selected"] = selected_text

        st.experimental_set_query_params(**params)


def sync_state_to_url() -> None:
    update_query_params(
        seed=st.session_state.seed,
        selected=st.session_state.selected_cells,
    )


# -----------------------------
# Seed + board generation
# -----------------------------

def stable_int_seed(seed_text: str) -> int:
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def random_seed() -> str:
    return hashlib.sha256(str(random.random()).encode("utf-8")).hexdigest()[:10]


@st.cache_data
def load_words() -> list[str]:
    df = pd.read_csv(WORDS_CSV)

    if "word" not in df.columns:
        raise ValueError("buzzwords.csv must contain a column named 'word'.")

    words = df["word"].dropna().astype(str).map(str.strip)
    words = [word for word in words if word]

    return list(dict.fromkeys(words))


def generate_board(words: list[str], seed_text: str) -> list[list[str]]:
    needed_words = TOTAL_CELLS - 1

    if len(words) < needed_words:
        raise ValueError(
            f"Need at least {needed_words} unique words in buzzwords.csv; "
            f"found {len(words)}."
        )

    rng = random.Random(stable_int_seed(seed_text))
    board_values = rng.sample(words, needed_words)
    board_values.insert(FREE_INDEX, FREE_SPACE)

    return [
        board_values[index: index + BOARD_SIZE]
        for index in range(0, TOTAL_CELLS, BOARD_SIZE)
    ]


def parse_selected_cells(selected_text: str) -> set[int]:
    selected = {FREE_INDEX}

    for part in selected_text.split(","):
        part = part.strip()

        if not part:
            continue

        try:
            index = int(part)
        except ValueError:
            continue

        if 0 <= index < TOTAL_CELLS:
            selected.add(index)

    return selected


# -----------------------------
# Bingo logic
# -----------------------------

def all_possible_lines() -> list[list[int]]:
    rows = [
        [row * BOARD_SIZE + col for col in range(BOARD_SIZE)]
        for row in range(BOARD_SIZE)
    ]

    columns = [
        [row * BOARD_SIZE + col for row in range(BOARD_SIZE)]
        for col in range(BOARD_SIZE)
    ]

    diagonal_a = [
        index * BOARD_SIZE + index
        for index in range(BOARD_SIZE)
    ]

    diagonal_b = [
        index * BOARD_SIZE + (BOARD_SIZE - 1 - index)
        for index in range(BOARD_SIZE)
    ]

    return rows + columns + [diagonal_a, diagonal_b]


def completed_lines(selected: set[int]) -> list[list[int]]:
    return [
        line
        for line in all_possible_lines()
        if all(index in selected for index in line)
    ]


def line_signature(line: list[int]) -> str:
    return ",".join(str(index) for index in line)


def current_line_signatures(lines: list[list[int]]) -> set[str]:
    return {
        line_signature(line)
        for line in lines
    }


def newly_completed_line_signatures(lines: list[list[int]]) -> set[str]:
    completed = current_line_signatures(lines)
    celebrated = st.session_state.get("celebrated_line_signatures", set())

    return completed - set(celebrated)


def mark_lines_as_celebrated(line_signatures: set[str]) -> None:
    celebrated = set(st.session_state.get("celebrated_line_signatures", set()))
    st.session_state.celebrated_line_signatures = celebrated | line_signatures


# -----------------------------
# State helpers and callbacks
# -----------------------------

def reset_celebrations() -> None:
    st.session_state.celebrated_line_signatures = set()


def reset_to_seed(seed: str) -> None:
    st.session_state.seed = seed
    st.session_state.seed_input = seed
    st.session_state.selected_cells = {FREE_INDEX}

    reset_celebrations()
    sync_state_to_url()


def toggle_cell(index: int) -> None:
    if index == FREE_INDEX:
        return

    selected = set(st.session_state.selected_cells)

    if index in selected:
        selected.remove(index)
    else:
        selected.add(index)

    selected.add(FREE_INDEX)

    st.session_state.selected_cells = selected
    sync_state_to_url()


def apply_seed() -> None:
    seed = st.session_state.seed_input.strip() or DEFAULT_SEED
    reset_to_seed(seed)


def randomize_seed() -> None:
    reset_to_seed(random_seed())


def reset_marks() -> None:
    st.session_state.selected_cells = {FREE_INDEX}

    reset_celebrations()
    sync_state_to_url()


def initialise_state_from_url() -> None:
    if "has_initialised" in st.session_state:
        return

    url_seed = get_query_value("seed", DEFAULT_SEED) or DEFAULT_SEED
    url_selected = get_query_value("selected", "")

    st.session_state.has_initialised = True
    st.session_state.seed = url_seed
    st.session_state.seed_input = url_seed
    st.session_state.selected_cells = parse_selected_cells(url_selected)
    st.session_state.celebrated_line_signatures = set()

    sync_state_to_url()


# -----------------------------
# Styling
# -----------------------------

def inject_css() -> None:
    st.markdown(
        """
        <style>
        /*
        Important:
        This targets only the keyed board container:
            st.container(key="bingo_board")

        Streamlit gives that container a class like:
            .st-key-bingo_board
        */

        .st-key-bingo_board {
            max-width: 560px;
            margin-left: auto;
            margin-right: auto;
        }

        .st-key-bingo_board div[data-testid="stHorizontalBlock"] {
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: nowrap !important;
            gap: 0.25rem !important;
        }

        .st-key-bingo_board div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
            min-width: 0 !important;
            width: 20% !important;
            flex: 0 0 calc(20% - 0.2rem) !important;
        }

        .st-key-bingo_board div[data-testid="column"] div.stButton {
            width: 100%;
            height: 100%;
        }

        .st-key-bingo_board div[data-testid="column"] div.stButton > button {
            width: 100%;
            min-width: 0;
            min-height: 88px;
            aspect-ratio: 1 / 1;
            white-space: normal;
            line-height: 1.1;
            font-weight: 700;
            border-radius: 12px;
            padding: 0.45rem;
            overflow-wrap: anywhere;
            word-break: break-word;
            hyphens: auto;
        }

        @media (max-width: 640px) {
            .block-container {
                padding-left: 0.35rem;
                padding-right: 0.35rem;
            }

            .st-key-bingo_board {
                max-width: 100%;
            }

            .st-key-bingo_board div[data-testid="stHorizontalBlock"] {
                gap: 0.12rem !important;
            }

            .st-key-bingo_board div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
                width: 20% !important;
                flex: 0 0 calc(20% - 0.1rem) !important;
            }

            .st-key-bingo_board div[data-testid="column"] div.stButton > button {
                min-height: 56px;
                font-size: 0.56rem;
                line-height: 1;
                border-radius: 8px;
                padding: 0.1rem;
            }
        }

        @media (max-width: 380px) {
            .st-key-bingo_board div[data-testid="column"] div.stButton > button {
                min-height: 50px;
                font-size: 0.5rem;
                padding: 0.06rem;
            }
        }

        @media print {
            header,
            footer,
            [data-testid="stSidebar"],
            [data-testid="stToolbar"] {
                display: none !important;
            }

            .block-container {
                padding-top: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------
# Rendering
# -----------------------------

def render_sidebar(words: list[str]) -> None:
    with st.sidebar:
        st.header("Card settings")

        st.text_input(
            "Seed",
            key="seed_input",
            help="The same seed always creates the same bingo card.",
        )

        col_a, col_b = st.columns(2)

        with col_a:
            st.button(
                "Apply seed",
                on_click=apply_seed,
                use_container_width=True,
            )

        with col_b:
            st.button(
                "Random",
                on_click=randomize_seed,
                use_container_width=True,
            )

        st.button(
            "Reset marked squares",
            on_click=reset_marks,
            use_container_width=True,
        )

        st.divider()

        st.write(f"Loaded **{len(words)}** buzzwords.")

        st.download_button(
            "Download word CSV",
            data=WORDS_CSV.read_text(encoding="utf-8"),
            file_name="buzzwords.csv",
            mime="text/csv",
            use_container_width=True,
        )


def cell_label(
    value: str,
    index: int,
    selected: set[int],
    winning_indexes: set[int],
) -> tuple[str, str]:
    if index in winning_indexes:
        return f"🎉 {value}", "primary"

    if index in selected:
        return f"✅ {value}", "primary"

    return value, "secondary"


def render_board(
    board: list[list[str]],
    selected: set[int],
    winning_indexes: set[int],
) -> None:
    with st.container(key="bingo_board"):
        for row_index, row in enumerate(board):
            columns = st.columns(
                [1] * BOARD_SIZE,
                gap="small",
                vertical_alignment="center",
            )

            for col_index, value in enumerate(row):
                index = row_index * BOARD_SIZE + col_index
                label, button_type = cell_label(
                    value=value,
                    index=index,
                    selected=selected,
                    winning_indexes=winning_indexes,
                )

                with columns[col_index]:
                    st.button(
                        label,
                        key=f"cell_{index}",
                        type=button_type,
                        disabled=index == FREE_INDEX,
                        on_click=toggle_cell,
                        args=(index,),
                        use_container_width=True,
                    )


def render_status(lines: list[list[int]], selected: set[int]) -> None:
    if lines:
        new_lines = newly_completed_line_signatures(lines)

        if new_lines:
            st.balloons()
            mark_lines_as_celebrated(new_lines)

        line_word = "line" if len(lines) == 1 else "lines"
        st.success(f"Bingo! You completed {len(lines)} {line_word}. 🎉")
    else:
        marked_count = len(selected) - 1
        st.info(f"Marked **{marked_count}** squares. Keep going!")


def render_footer(selected: set[int]) -> None:
    share_suffix = f"?seed={st.session_state.seed}"

    selected_text = selected_to_query_param(selected)
    if selected_text:
        share_suffix += f"&selected={selected_text}"

    st.caption("Tip: use your browser's print command to save a card as PDF.")
    st.caption(f"Share path: `{share_suffix}`")


# -----------------------------
# App
# -----------------------------

def main() -> None:
    initialise_state_from_url()
    inject_css()

    words = load_words()
    board = generate_board(words, st.session_state.seed)

    selected = set(st.session_state.selected_cells)
    lines = completed_lines(selected)
    winning_indexes = {
        index
        for line in lines
        for index in line
    }

    st.title("🎯 Buzzword Bingo")
    st.caption(
        "Click a square to mark it. The app uses st.session_state for clicks "
        "and mirrors the state into the URL."
    )

    render_sidebar(words)
    render_board(board, selected, winning_indexes)
    render_status(lines, selected)
    render_footer(selected)


if __name__ == "__main__":
    main()