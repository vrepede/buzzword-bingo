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

st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="centered")


# -----------------------------
# URL/query-param helpers
# -----------------------------

def get_query_value(name: str, default: str = "") -> str:
    """Read a single value from the URL query string."""
    try:
        value = st.query_params.get(name, default)
    except Exception:
        params = st.experimental_get_query_params()
        values = params.get(name, [default])
        value = values[0] if values else default

    if isinstance(value, list):
        value = value[0] if value else default

    return str(value).strip()


def selected_param(selected: set[int]) -> str:
    """Serialize selected cells for the URL, excluding the free square."""
    return ",".join(
        str(index)
        for index in sorted(selected)
        if index != FREE_INDEX
    )


def set_query_params(seed: str, selected: set[int]) -> None:
    """Mirror current Streamlit state into the URL query params."""
    selected_text = selected_param(selected)

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
    set_query_params(
        st.session_state.seed,
        st.session_state.selected_cells,
    )


# -----------------------------
# Board generation
# -----------------------------

def stable_int_seed(seed_text: str) -> int:
    """Convert any text seed into a deterministic integer seed."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


@st.cache_data
def load_words() -> list[str]:
    df = pd.read_csv(WORDS_CSV)

    if "word" not in df.columns:
        raise ValueError("buzzwords.csv must contain a column named 'word'.")

    words = df["word"].dropna().astype(str).map(str.strip)
    words = [word for word in words if word]

    # Keep first occurrence while removing duplicates.
    return list(dict.fromkeys(words))


def generate_board(
    words: list[str],
    seed_text: str,
    board_size: int = BOARD_SIZE,
) -> list[list[str]]:
    total_cells = board_size * board_size
    free_index = total_cells // 2
    needed_words = total_cells - 1

    if len(words) < needed_words:
        raise ValueError(
            f"Need at least {needed_words} unique words in buzzwords.csv; "
            f"found {len(words)}."
        )

    rng = random.Random(stable_int_seed(seed_text))
    selected_words = rng.sample(words, needed_words)
    selected_words.insert(free_index, FREE_SPACE)

    return [
        selected_words[i: i + board_size]
        for i in range(0, total_cells, board_size)
    ]


def parse_selected_cells(
    selected_text: str,
    board_size: int = BOARD_SIZE,
) -> set[int]:
    """Read selected cell indexes from the URL, always including the free square."""
    total_cells = board_size * board_size
    free_index = total_cells // 2
    selected = {free_index}

    for part in selected_text.split(","):
        part = part.strip()
        if not part:
            continue

        try:
            index = int(part)
        except ValueError:
            continue

        if 0 <= index < total_cells:
            selected.add(index)

    return selected


# -----------------------------
# Bingo logic
# -----------------------------

def all_possible_lines(board_size: int = BOARD_SIZE) -> list[list[int]]:
    """Return all rows, columns, and diagonals."""
    lines: list[list[int]] = []

    # Rows
    for row in range(board_size):
        lines.append([
            row * board_size + col
            for col in range(board_size)
        ])

    # Columns
    for col in range(board_size):
        lines.append([
            row * board_size + col
            for row in range(board_size)
        ])

    # Diagonals
    lines.append([
        i * board_size + i
        for i in range(board_size)
    ])

    lines.append([
        i * board_size + (board_size - 1 - i)
        for i in range(board_size)
    ])

    return lines


def completed_lines(
    selected: set[int],
    board_size: int = BOARD_SIZE,
) -> list[list[int]]:
    """Return completed rows, columns, and diagonals."""
    return [
        line
        for line in all_possible_lines(board_size)
        if all(index in selected for index in line)
    ]


def line_signature(line: list[int]) -> str:
    """Stable ID for a completed line."""
    return ",".join(str(index) for index in line)


def get_new_completed_line_signatures(lines: list[list[int]]) -> set[str]:
    """
    Return completed lines that have not yet triggered balloons.

    This is the important part: celebration state is based on completed lines,
    not on the full selected-cell set. That means selecting extra squares after
    a bingo does not re-trigger balloons.
    """
    current_line_signatures = {
        line_signature(line)
        for line in lines
    }

    already_celebrated = set(
        st.session_state.get("celebrated_line_signatures", set())
    )

    return current_line_signatures - already_celebrated


def mark_lines_as_celebrated(line_signatures: set[str]) -> None:
    already_celebrated = set(
        st.session_state.get("celebrated_line_signatures", set())
    )

    st.session_state.celebrated_line_signatures = (
        already_celebrated | line_signatures
    )


# -----------------------------
# State callbacks
# -----------------------------

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


def reset_celebrations() -> None:
    st.session_state.celebrated_line_signatures = set()


def apply_seed() -> None:
    seed = st.session_state.seed_input.strip() or DEFAULT_SEED

    st.session_state.seed = seed
    st.session_state.selected_cells = {FREE_INDEX}

    reset_celebrations()
    sync_state_to_url()


def randomize_seed() -> None:
    seed = hashlib.sha256(str(random.random()).encode()).hexdigest()[:10]

    st.session_state.seed = seed
    st.session_state.seed_input = seed
    st.session_state.selected_cells = {FREE_INDEX}

    reset_celebrations()
    sync_state_to_url()


def reset_marks() -> None:
    st.session_state.selected_cells = {FREE_INDEX}

    reset_celebrations()
    sync_state_to_url()


# -----------------------------
# Initial state
# -----------------------------

url_seed = get_query_value("seed", DEFAULT_SEED) or DEFAULT_SEED
url_selected = get_query_value("selected", "")
url_signature = (url_seed, url_selected)

if "url_signature" not in st.session_state:
    st.session_state.url_signature = url_signature
    st.session_state.seed = url_seed
    st.session_state.seed_input = url_seed
    st.session_state.selected_cells = parse_selected_cells(url_selected)
    st.session_state.celebrated_line_signatures = set()

    sync_state_to_url()

if "celebrated_line_signatures" not in st.session_state:
    st.session_state.celebrated_line_signatures = set()


# -----------------------------
# Data + derived state
# -----------------------------

words = load_words()
board = generate_board(words, st.session_state.seed)

selected = set(st.session_state.selected_cells)
lines = completed_lines(selected)
winning_indexes = {
    index
    for line in lines
    for index in line
}
has_bingo = bool(lines)


# -----------------------------
# UI
# -----------------------------

st.title("🎯 Buzzword Bingo")
st.caption("A deterministic bingo card generated from a seed in the URL.")

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


st.markdown(
    """
    <style>
    div[data-testid="column"] div.stButton > button {
        min-height: 96px;
        width: 100%;
        white-space: normal;
        line-height: 1.15;
        font-weight: 700;
        border-radius: 12px;
        padding: 0.55rem;
        aspect-ratio: 1 / 1;
    }

    div[data-testid="stVerticalBlock"]:has(> div[data-testid="stHorizontalBlock"]) {
        gap: 0.35rem;
    }

    @media (max-width: 640px) {
        div[data-testid="column"] div.stButton > button {
            min-height: 70px;
            font-size: 0.72rem;
            line-height: 1.05;
            padding: 0.25rem;
        }

        div[data-testid="column"] {
            min-width: 0 !important;
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

st.subheader(f"Card seed: `{st.session_state.seed}`")
st.caption(
    "Click a square to mark it. The app uses st.session_state for clicks "
    "and mirrors the state into the URL."
)


# -----------------------------
# Board rendering
# -----------------------------

board_container = st.container(border=False)

with board_container:
    for row_index, row in enumerate(board):
        # Each row is grouped in a vertical container.
        # The row itself is split into equal-width columns for mobile-friendly sizing.
        with st.container(border=False):
            columns = st.columns(
                [1] * BOARD_SIZE,
                gap="small",
                vertical_alignment="center",
            )

            for col_index, value in enumerate(row):
                index = row_index * BOARD_SIZE + col_index

                is_free = index == FREE_INDEX
                is_selected = index in selected
                is_winning = index in winning_indexes

                if is_winning:
                    label = f"🎉 {value}"
                    button_type = "primary"
                elif is_selected:
                    label = f"✅ {value}"
                    button_type = "primary"
                else:
                    label = value
                    button_type = "secondary"

                with columns[col_index]:
                    with st.container(border=False):
                        st.button(
                            label,
                            key=f"cell_{index}",
                            type=button_type,
                            disabled=is_free,
                            on_click=toggle_cell,
                            args=(index,),
                            use_container_width=True,
                        )


# -----------------------------
# Celebration + status
# -----------------------------

if has_bingo:
    new_completed_lines = get_new_completed_line_signatures(lines)

    if new_completed_lines:
        st.balloons()
        mark_lines_as_celebrated(new_completed_lines)

    line_word = "line" if len(lines) == 1 else "lines"
    st.success(f"Bingo! You completed {len(lines)} {line_word}. 🎉")
else:
    marked_count = len(selected) - 1
    st.info(f"Marked **{marked_count}** squares. Keep going!")


# -----------------------------
# Share hint
# -----------------------------

share_suffix = f"?seed={st.session_state.seed}"

selected_text = selected_param(selected)
if selected_text:
    share_suffix += f"&selected={selected_text}"

st.write("")

st.info(
    "Share this exact card by copying the page URL. "
    f"The important part is `{share_suffix}`."
)

st.caption("Tip: use your browser's print command to save a card as PDF.")