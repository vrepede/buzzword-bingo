import hashlib
import html
import json
import random
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_TITLE = "Buzzword Bingo"
WORDS_CSV = Path(__file__).parent / "buzzwords.csv"

BOARD_SIZE = 5
FREE_SPACE = "Vizrt Days 2026"
DEFAULT_SEED = "vizrt-days-2026"

TOTAL_CELLS = BOARD_SIZE * BOARD_SIZE
FREE_INDEX = TOTAL_CELLS // 2

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# -----------------------------
# Query param helpers
# -----------------------------

def get_query_value(name: str, default: str = "") -> str:
    """Read one value from the URL query string."""
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
    """Serialize selected cells for the URL, excluding the free square."""
    return ",".join(
        str(index)
        for index in sorted(selected)
        if index != FREE_INDEX
    )


def update_query_params(seed: str, selected: set[int]) -> None:
    """Mirror Streamlit-side seed/reset state into URL query params."""
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


# -----------------------------
# Seed + board generation
# -----------------------------

def stable_int_seed(seed_text: str) -> int:
    """Convert any text seed into a deterministic integer."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def random_seed() -> str:
    """Generate a short random seed."""
    return hashlib.sha256(str(random.random()).encode("utf-8")).hexdigest()[:10]


@st.cache_data
def load_words() -> list[str]:
    """Load and deduplicate buzzwords from buzzwords.csv."""
    df = pd.read_csv(WORDS_CSV)

    if "word" not in df.columns:
        raise ValueError("buzzwords.csv must contain a column named 'word'.")

    words = df["word"].dropna().astype(str).map(str.strip)
    words = [word for word in words if word]

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(words))


def generate_board(words: list[str], seed_text: str) -> list[str]:
    """Generate a deterministic flat bingo board from the seed."""
    needed_words = TOTAL_CELLS - 1

    if len(words) < needed_words:
        raise ValueError(
            f"Need at least {needed_words} unique words in buzzwords.csv; "
            f"found {len(words)}."
        )

    rng = random.Random(stable_int_seed(seed_text))
    board_values = rng.sample(words, needed_words)
    board_values.insert(FREE_INDEX, FREE_SPACE)

    return board_values


def parse_selected_cells(selected_text: str) -> set[int]:
    """Parse selected indexes from URL query params."""
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
# Bingo line generation
# -----------------------------

def all_possible_lines() -> list[list[int]]:
    """Return all rows, columns, and diagonals."""
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


# -----------------------------
# Streamlit state
# -----------------------------

def reset_to_seed(seed: str) -> None:
    st.session_state.seed = seed
    st.session_state.seed_input = seed
    st.session_state.selected_cells = {FREE_INDEX}
    update_query_params(seed, st.session_state.selected_cells)


def apply_seed() -> None:
    seed = st.session_state.seed_input.strip() or DEFAULT_SEED
    reset_to_seed(seed)


def randomize_seed() -> None:
    reset_to_seed(random_seed())


def reset_marks() -> None:
    st.session_state.selected_cells = {FREE_INDEX}
    update_query_params(st.session_state.seed, st.session_state.selected_cells)


def initialise_state_from_url() -> None:
    """Initialise Streamlit session state once from URL params."""
    if "has_initialised" in st.session_state:
        return

    url_seed = get_query_value("seed", DEFAULT_SEED) or DEFAULT_SEED
    url_selected = get_query_value("selected", "")

    st.session_state.has_initialised = True
    st.session_state.seed = url_seed
    st.session_state.seed_input = url_seed
    st.session_state.selected_cells = parse_selected_cells(url_selected)


# -----------------------------
# HTML board
# -----------------------------

def render_html_board(
    board_values: list[str],
    seed: str,
    selected: set[int],
) -> None:
    """
    Render a pure HTML/CSS/JS bingo grid.

    The grid interaction is fully client-side:
    - no Streamlit buttons
    - no Streamlit columns
    - no Streamlit containers
    - no rerun on each click
    - selected cells are mirrored into the browser URL
    - celebration fires once per newly completed line
    """
    safe_board = [html.escape(value) for value in board_values]

    payload = {
        "seed": seed,
        "boardSize": BOARD_SIZE,
        "freeIndex": FREE_INDEX,
        "freeSpace": FREE_SPACE,
        "board": safe_board,
        "initialSelected": sorted(selected),
        "lines": all_possible_lines(),
    }

    component_html = f"""
<!doctype html>
<html>
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />

<style>
:root {{
    --bg: #ffffff;
    --card: #f8fafc;
    --card-border: #cbd5e1;
    --card-text: #0f172a;
    --selected: #2563eb;
    --selected-border: #1d4ed8;
    --selected-text: #ffffff;
    --winning: #f59e0b;
    --winning-border: #d97706;
    --winning-text: #111827;
    --muted: #64748b;
}}

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    padding: 0;
    background: transparent;
    font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}

.bingo-shell {{
    width: min(100%, 560px);
    margin: 0 auto;
    padding: 4px;
}}

.bingo-grid {{
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: 8px;
    width: 100%;
}}

.bingo-cell {{
    appearance: none;
    border: 1px solid var(--card-border);
    background: var(--card);
    color: var(--card-text);
    border-radius: 14px;
    aspect-ratio: 1 / 1;
    width: 100%;
    min-width: 0;
    padding: 8px;
    cursor: pointer;
    font-weight: 750;
    font-size: clamp(0.52rem, 2.35vw, 0.92rem);
    line-height: 1.08;
    text-align: center;
    overflow-wrap: anywhere;
    word-break: break-word;
    hyphens: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    transition:
        transform 120ms ease,
        border-color 120ms ease,
        background-color 120ms ease,
        color 120ms ease;
}}

.bingo-cell:hover {{
    transform: translateY(-1px);
}}

.bingo-cell:active {{
    transform: scale(0.98);
}}

.bingo-cell.selected {{
    background: var(--selected);
    border-color: var(--selected-border);
    color: var(--selected-text);
}}

.bingo-cell.winning {{
    background: var(--winning);
    border-color: var(--winning-border);
    color: var(--winning-text);
}}

.bingo-cell.free {{
    cursor: default;
}}

.status {{
    margin-top: 12px;
    padding: 10px 12px;
    border-radius: 12px;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    color: #1e3a8a;
    font-size: 0.95rem;
    line-height: 1.35;
}}

.status.success {{
    background: #ecfdf5;
    border-color: #a7f3d0;
    color: #065f46;
}}

.toolbar {{
    display: flex;
    gap: 8px;
    margin-top: 10px;
}}

.toolbar button {{
    border: 1px solid #cbd5e1;
    background: #ffffff;
    color: #0f172a;
    border-radius: 10px;
    padding: 8px 10px;
    font-weight: 700;
    cursor: pointer;
}}

.toolbar button:hover {{
    background: #f8fafc;
}}

.share {{
    margin-top: 8px;
    color: var(--muted);
    font-size: 0.78rem;
    line-height: 1.3;
    overflow-wrap: anywhere;
}}

.confetti-layer {{
    pointer-events: none;
    position: fixed;
    inset: 0;
    overflow: hidden;
    z-index: 999999;
}}

.confetti {{
    position: absolute;
    top: -12px;
    width: 8px;
    height: 14px;
    border-radius: 2px;
    opacity: 0.95;
    animation: fall 1400ms linear forwards;
}}

@keyframes fall {{
    0% {{
        transform: translateY(-20px) rotate(0deg);
    }}
    100% {{
        transform: translateY(105vh) rotate(720deg);
    }}
}}

@media (max-width: 460px) {{
    .bingo-shell {{
        padding: 2px;
    }}

    .bingo-grid {{
        gap: 4px;
    }}

    .bingo-cell {{
        border-radius: 9px;
        padding: 3px;
        font-size: clamp(0.46rem, 2.8vw, 0.62rem);
        line-height: 1;
    }}

    .status {{
        font-size: 0.82rem;
        padding: 8px;
    }}

    .toolbar button {{
        font-size: 0.78rem;
        padding: 7px 8px;
    }}
}}

@media (prefers-color-scheme: dark) {{
    :root {{
        --bg: #0f172a;
        --card: #1e293b;
        --card-border: #334155;
        --card-text: #f8fafc;
        --selected: #2563eb;
        --selected-border: #60a5fa;
        --selected-text: #ffffff;
        --winning: #fbbf24;
        --winning-border: #f59e0b;
        --winning-text: #111827;
        --muted: #94a3b8;
    }}

    .toolbar button {{
        background: #1e293b;
        color: #f8fafc;
        border-color: #334155;
    }}

    .toolbar button:hover {{
        background: #334155;
    }}
}}
</style>
</head>

<body>
<div class="bingo-shell">
    <div id="bingo-grid" class="bingo-grid"></div>

    <div class="toolbar">
        <button type="button" id="reset-button">Reset marks</button>
        <button type="button" id="copy-button">Copy share URL</button>
    </div>

    <div id="status" class="status"></div>
    <div id="share" class="share"></div>
</div>

<div id="confetti-layer" class="confetti-layer"></div>

<script>
const DATA = {json.dumps(payload)};

const grid = document.getElementById("bingo-grid");
const statusBox = document.getElementById("status");
const shareBox = document.getElementById("share");
const resetButton = document.getElementById("reset-button");
const copyButton = document.getElementById("copy-button");
const confettiLayer = document.getElementById("confetti-layer");

const seed = DATA.seed;
const board = DATA.board;
const boardSize = DATA.boardSize;
const freeIndex = DATA.freeIndex;
const lines = DATA.lines;

const selected = new Set(DATA.initialSelected);
selected.add(freeIndex);

const celebrationStorageKey = `buzzword-bingo-celebrated:${{seed}}`;

function getCelebratedLines() {{
    try {{
        const raw = window.localStorage.getItem(celebrationStorageKey);
        return new Set(raw ? JSON.parse(raw) : []);
    }} catch {{
        return new Set();
    }}
}}

function setCelebratedLines(values) {{
    try {{
        window.localStorage.setItem(
            celebrationStorageKey,
            JSON.stringify([...values])
        );
    }} catch {{
        // Ignore localStorage failures.
    }}
}}

function selectedParam() {{
    return [...selected]
        .filter(index => index !== freeIndex)
        .sort((a, b) => a - b)
        .join(",");
}}

function currentUrl() {{
    const params = new URLSearchParams();
    params.set("seed", seed);

    const selectedText = selectedParam();
    if (selectedText) {{
        params.set("selected", selectedText);
    }}

    const parentLocation = window.parent.location;
    return `${{parentLocation.origin}}${{parentLocation.pathname}}?${{params.toString()}}`;
}}

function syncUrl() {{
    const params = new URLSearchParams();
    params.set("seed", seed);

    const selectedText = selectedParam();
    if (selectedText) {{
        params.set("selected", selectedText);
    }}

    const newUrl = `${{window.parent.location.pathname}}?${{params.toString()}}`;

    try {{
        window.parent.history.replaceState(null, "", newUrl);
    }} catch {{
        // If parent history is unavailable, silently continue.
        // The internal state still works.
    }}

    shareBox.textContent = `Share path: ?${{params.toString()}}`;
}}

function lineSignature(line) {{
    return line.join(",");
}}

function getCompletedLines() {{
    return lines.filter(line => line.every(index => selected.has(index)));
}}

function getWinningIndexes(completedLines) {{
    const indexes = new Set();

    for (const line of completedLines) {{
        for (const index of line) {{
            indexes.add(index);
        }}
    }}

    return indexes;
}}

function makeCell(index, value) {{
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "bingo-cell";
    cell.dataset.index = String(index);
    cell.textContent = value;

    if (index === freeIndex) {{
        cell.classList.add("free");
        cell.disabled = true;
    }}

    cell.addEventListener("click", () => {{
        toggleCell(index);
    }});

    return cell;
}}

function renderGrid() {{
    grid.innerHTML = "";

    board.forEach((value, index) => {{
        grid.appendChild(makeCell(index, value));
    }});

    renderState();
}}

function renderState() {{
    selected.add(freeIndex);

    const completedLines = getCompletedLines();
    const winningIndexes = getWinningIndexes(completedLines);

    document.querySelectorAll(".bingo-cell").forEach(cell => {{
        const index = Number(cell.dataset.index);
        const rawValue = board[index];

        cell.classList.toggle("selected", selected.has(index));
        cell.classList.toggle("winning", winningIndexes.has(index));

        if (winningIndexes.has(index)) {{
            cell.textContent = `🎉 ${{rawValue}}`;
        }} else if (selected.has(index)) {{
            cell.textContent = index === freeIndex ? rawValue : `✅ ${{rawValue}}`;
        }} else {{
            cell.textContent = rawValue;
        }}
    }});

    const markedCount = selected.size - 1;

    if (completedLines.length > 0) {{
        const lineWord = completedLines.length === 1 ? "line" : "lines";
        statusBox.classList.add("success");
        statusBox.textContent = `Bingo! You completed ${{completedLines.length}} ${{lineWord}}. 🎉`;
    }} else {{
        statusBox.classList.remove("success");
        statusBox.textContent = `Marked ${{markedCount}} squares. Keep going!`;
    }}

    celebrateNewLines(completedLines);
    syncUrl();
}}

function toggleCell(index) {{
    if (index === freeIndex) {{
        return;
    }}

    if (selected.has(index)) {{
        selected.delete(index);
    }} else {{
        selected.add(index);
    }}

    selected.add(freeIndex);
    renderState();
}}

function resetMarks() {{
    selected.clear();
    selected.add(freeIndex);

    try {{
        window.localStorage.removeItem(celebrationStorageKey);
    }} catch {{
        // Ignore localStorage failures.
    }}

    renderState();
}}

function celebrateNewLines(completedLines) {{
    const celebrated = getCelebratedLines();
    const completedSignatures = completedLines.map(lineSignature);
    const newSignatures = completedSignatures.filter(signature => !celebrated.has(signature));

    if (newSignatures.length === 0) {{
        return;
    }}

    newSignatures.forEach(signature => celebrated.add(signature));
    setCelebratedLines(celebrated);
    fireConfetti();
}}

function fireConfetti() {{
    const colors = [
        "#2563eb",
        "#f59e0b",
        "#10b981",
        "#ef4444",
        "#8b5cf6",
        "#ec4899"
    ];

    const count = 90;

    for (let i = 0; i < count; i++) {{
        const piece = document.createElement("div");
        piece.className = "confetti";
        piece.style.left = `${{Math.random() * 100}}vw`;
        piece.style.background = colors[Math.floor(Math.random() * colors.length)];
        piece.style.animationDelay = `${{Math.random() * 220}}ms`;
        piece.style.animationDuration = `${{900 + Math.random() * 900}}ms`;
        piece.style.transform = `rotate(${{Math.random() * 360}}deg)`;

        confettiLayer.appendChild(piece);

        window.setTimeout(() => {{
            piece.remove();
        }}, 2100);
    }}
}}

async function copyShareUrl() {{
    const url = currentUrl();

    try {{
        await navigator.clipboard.writeText(url);
        copyButton.textContent = "Copied!";
        window.setTimeout(() => {{
            copyButton.textContent = "Copy share URL";
        }}, 1200);
    }} catch {{
        copyButton.textContent = "Copy failed";
        window.setTimeout(() => {{
            copyButton.textContent = "Copy share URL";
        }}, 1200);
    }}
}}

resetButton.addEventListener("click", resetMarks);
copyButton.addEventListener("click", copyShareUrl);

renderGrid();
</script>
</body>
</html>
"""

    components.html(component_html, height=720, scrolling=False)


# -----------------------------
# Sidebar
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
            help=(
                "This resets the URL state. The HTML board also has its own "
                "reset button for instant client-side reset."
            ),
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


# -----------------------------
# App
# -----------------------------

def main() -> None:
    initialise_state_from_url()

    words = load_words()
    board_values = generate_board(words, st.session_state.seed)
    selected = set(st.session_state.selected_cells)

    st.header("🎯 Buzzword Bingo")
    st.markdown(
        """
        🔥 **Welcome to Buzzword Bingo: Vizrt Days 2026 Edition!** 🔥

        ✨ Like bingo, but with more AI, real-time graphics, and visual storytelling. ✨
        """
    )

    render_sidebar(words)

    render_html_board(
        board_values=board_values,
        seed=st.session_state.seed,
        selected=selected,
    )

    st.caption("Tip: use your browser's print command to save a card as PDF.")


if __name__ == "__main__":
    main()