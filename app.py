import hashlib
import html
import random
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import streamlit as st

APP_TITLE = "Buzzword Bingo"
WORDS_CSV = Path(__file__).parent / "buzzwords.csv"
BOARD_SIZE = 5
FREE_SPACE = "FREE SPACE"


st.set_page_config(page_title=APP_TITLE, page_icon="🎯", layout="centered")


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


def set_query_seed(seed: str) -> None:
    """Write ?seed=... into the URL and clear selected cells for the new card."""
    try:
        st.query_params.clear()
        st.query_params["seed"] = seed
    except Exception:
        st.experimental_set_query_params(seed=seed)


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

    # Keep the first occurrence while removing duplicates.
    return list(dict.fromkeys(words))


def generate_board(words: list[str], seed_text: str, board_size: int = BOARD_SIZE) -> list[list[str]]:
    total_cells = board_size * board_size
    free_index = total_cells // 2
    needed_words = total_cells - 1

    if len(words) < needed_words:
        raise ValueError(
            f"Need at least {needed_words} unique words in buzzwords.csv; found {len(words)}."
        )

    rng = random.Random(stable_int_seed(seed_text))
    selected = rng.sample(words, needed_words)
    selected.insert(free_index, FREE_SPACE)

    return [selected[i : i + board_size] for i in range(0, total_cells, board_size)]


def parse_selected_cells(selected_text: str, board_size: int = BOARD_SIZE) -> set[int]:
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


def make_card_url(seed: str, selected: set[int]) -> str:
    """Create a relative URL containing the seed and currently selected cells."""
    total_cells = BOARD_SIZE * BOARD_SIZE
    free_index = total_cells // 2
    selected_without_free = sorted(index for index in selected if index != free_index)

    query = {"seed": seed}
    if selected_without_free:
        query["selected"] = ",".join(str(index) for index in selected_without_free)
    return "?" + urlencode(query)


def toggle_url(seed: str, selected: set[int], index: int) -> str:
    """Return the URL that toggles one cell on or off."""
    total_cells = BOARD_SIZE * BOARD_SIZE
    free_index = total_cells // 2
    next_selected = set(selected)

    if index != free_index:
        if index in next_selected:
            next_selected.remove(index)
        else:
            next_selected.add(index)

    return make_card_url(seed, next_selected)


def completed_lines(selected: set[int], board_size: int = BOARD_SIZE) -> list[list[int]]:
    """Return completed rows, columns, and diagonals."""
    lines = []

    for row in range(board_size):
        lines.append([row * board_size + col for col in range(board_size)])

    for col in range(board_size):
        lines.append([row * board_size + col for row in range(board_size)])

    lines.append([i * board_size + i for i in range(board_size)])
    lines.append([i * board_size + (board_size - 1 - i) for i in range(board_size)])

    return [line for line in lines if all(index in selected for index in line)]


def board_html(board: list[list[str]], seed: str, selected: set[int], winning_indexes: set[int]) -> str:
    cells = []

    for row_index, row in enumerate(board):
        for col_index, value in enumerate(row):
            index = row_index * BOARD_SIZE + col_index
            classes = ["cell"]
            if value == FREE_SPACE:
                classes.append("free")
            if index in selected:
                classes.append("selected")
            if index in winning_indexes:
                classes.append("winning")

            href = html.escape(toggle_url(seed, selected, index), quote=True)
            label = html.escape(value)
            aria_label = html.escape(f"Toggle {value}", quote=True)
            cells.append(
                f'<a class="{" ".join(classes)}" href="{href}" aria-label="{aria_label}">{label}</a>'
            )

    return f'<div class="bingo-board">{"".join(cells)}</div>'


st.title("🎯 Buzzword Bingo")
st.caption("A deterministic bingo card generated from a seed in the URL.")

words = load_words()
url_seed = get_query_value("seed")
selected_text = get_query_value("selected")

with st.sidebar:
    st.header("Card settings")
    seed = st.text_input(
        "Seed",
        value=url_seed or "team-all-hands",
        help="The same seed always creates the same bingo card.",
    ).strip()

    col_a, col_b = st.columns(2)
    with col_a:
        apply_seed = st.button("Apply seed", use_container_width=True)
    with col_b:
        random_seed = st.button("Random", use_container_width=True)

    if random_seed:
        seed = hashlib.sha256(str(random.random()).encode()).hexdigest()[:10]
        set_query_seed(seed)
        st.rerun()

    if apply_seed:
        set_query_seed(seed)
        st.rerun()

    st.divider()
    st.write(f"Loaded **{len(words)}** buzzwords.")
    st.download_button(
        "Download word CSV",
        data=WORDS_CSV.read_text(encoding="utf-8"),
        file_name="buzzwords.csv",
        mime="text/csv",
        use_container_width=True,
    )

if not seed:
    seed = "team-all-hands"

# Keep URL populated on first load.
if not url_seed:
    set_query_seed(seed)

board = generate_board(words, seed)
selected = parse_selected_cells(selected_text)
lines = completed_lines(selected)
winning_indexes = {index for line in lines for index in line}
has_bingo = bool(lines)

st.markdown(
    """
    <style>
    .bingo-board {
        display: grid;
        grid-template-columns: repeat(5, minmax(80px, 1fr));
        gap: 8px;
        margin-top: 1.25rem;
    }
    .cell {
        min-height: 95px;
        border: 2px solid rgba(49, 51, 63, 0.25);
        border-radius: 12px;
        padding: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        text-align: center;
        font-weight: 700;
        line-height: 1.15;
        background: rgba(250, 250, 250, 0.88);
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        user-select: none;
        text-decoration: none !important;
        color: inherit !important;
        transition: transform 120ms ease, background 120ms ease, border-color 120ms ease;
    }
    .cell:hover {
        transform: translateY(-1px);
        border-color: rgba(255, 75, 75, 0.65);
    }
    .cell.selected {
        background: rgba(255, 75, 75, 0.20);
        border-color: rgba(255, 75, 75, 0.85);
    }
    .cell.free {
        border-style: dashed;
        background: rgba(255, 237, 160, 0.85);
    }
    .cell.free.selected {
        background: rgba(255, 237, 160, 0.95);
    }
    .cell.winning {
        background: rgba(36, 171, 96, 0.24);
        border-color: rgba(36, 171, 96, 0.95);
        box-shadow: 0 0 0 3px rgba(36, 171, 96, 0.18);
    }
    @media print {
        header, footer, [data-testid="stSidebar"], [data-testid="stToolbar"] {
            display: none !important;
        }
        .block-container {
            padding-top: 1rem;
        }
        .cell {
            border-color: #333;
            box-shadow: none;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.subheader(f"Card seed: `{seed}`")
st.caption("Click a square to mark it. The selection is saved in the URL, so the card can be shared mid-game.")
st.markdown(board_html(board, seed, selected, winning_indexes), unsafe_allow_html=True)

if has_bingo:
    bingo_key = f"{seed}:{','.join(str(i) for i in sorted(selected))}"
    if st.session_state.get("last_bingo_key") != bingo_key:
        st.balloons()
        st.session_state["last_bingo_key"] = bingo_key

    line_word = "line" if len(lines) == 1 else "lines"
    st.success(f"Bingo! You completed {len(lines)} {line_word}. 🎉")
else:
    marked_count = len(selected) - 1  # Exclude the free square.
    st.info(f"Marked **{marked_count}** squares. Keep going!")

st.write("")
st.info(
    "Share this exact card by copying the page URL. "
    f"The important part is `{make_card_url(seed, selected)}`."
)
st.caption("Tip: use your browser's print command to save a card as PDF.")
