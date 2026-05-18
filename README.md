# Buzzword Bingo

A tiny Streamlit app that generates a deterministic 5x5 buzzword bingo card from a seed in the URL.

## How it works

- Words live in `buzzwords.csv`.
- The URL parameter `?seed=...` controls the card.
- The same seed always generates the same board.
- The centre square is `FREE SPACE`.

Example:

```text
https://your-app.streamlit.app/?seed=team-all-hands
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a public GitHub repository.
2. Add these files to the repository:
   - `app.py`
   - `buzzwords.csv`
   - `requirements.txt`
3. Go to Streamlit Community Cloud.
4. Create a new app from the GitHub repository.
5. Set the main file path to `app.py`.
6. Deploy.

## Customize the words

Edit `buzzwords.csv`. Keep the column header as:

```csv
word
```

You need at least 24 unique words for a 5x5 card with a free centre square.
