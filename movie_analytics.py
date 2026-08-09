"""
Movie Data Analytics Platform
=============================

A beginner-friendly Python tool that:

    1. Loads a movie CSV dataset (any user-provided CSV).
    2. Cleans it (missing values, duplicates, bad numbers, column names).
    3. Runs core analytics (overview, top rated, genres, popularity, votes,
       release trend, rating distribution).
    4. Generates professional charts saved as high-resolution PNGs.
    5. Produces a data-quality report and a human-readable summary.

The script automatically detects which columns exist in the dataset and
only runs the analyses that the data can actually support. It never relies
on hard-coded movie results.

Usage
-----
    python movie_analytics.py                  # uses data/movies.csv
    python movie_analytics.py path/to/file.csv # uses your own dataset

The module can also be imported and reused (for example by a Flask app):

    from movie_analytics import run_analysis
    results = run_analysis("data/movies.csv")
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Matplotlib must pick a non-interactive backend when running in a terminal
# or from a server so that charts can be saved without a display window.
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Column aliases: each logical field can appear under several names in the
# user's CSV. The loader maps any of these to one canonical field.
COLUMN_ALIASES = {
    "title": ["title", "name", "movie_title", "film", "movie"],
    "genres": ["genre", "genres"],
    "rating": [
        "rating",
        "score",
        "vote_average",
        "average_rating",
        "imdb_rating",
        "rating_score",
    ],
    "votes": ["votes", "vote_count", "num_votes", "imdb_votes"],
    "popularity": ["popularity"],
    "year": ["year", "release_year", "year_of_release"],
    "revenue": ["revenue", "gross", "box_office"],
    "runtime": ["runtime", "duration", "length"],
}

# Chart style: readable fonts, clean look, professional colours.
plt.rcParams.update(
    {
        "figure.dpi": 100,
        "savefig.dpi": 150,
        "font.size": 11,
        "axes.titlesize": 15,
        "axes.titleweight": "bold",
        "axes.labelsize": 12,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "figure.autolayout": True,
    }
)

# ---------------------------------------------------------------------------
# Loading & cleaning helpers
# ---------------------------------------------------------------------------


def load_csv(file_path):
    """
    Safely load a CSV file into a pandas DataFrame.

    Raises a FileNotFoundError (with a friendly message) if the file does
    not exist and a ValueError if the file cannot be parsed as CSV.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(
            "CSV file not found: '{}'. Please check the path.".format(path)
        )
    try:
        return _read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            return _read_csv(path, encoding="latin-1")
        except UnicodeDecodeError:
            return _read_csv(path)
    except Exception as exc:  # noqa: BLE001 - we re-raise a clear error below
        raise ValueError(
            "Could not read '{}' as a CSV file. Error: {}".format(path, exc)
        )


def _read_csv(path, encoding=None):
    """
    Read a CSV strictly first; if a row is malformed, fall back to skipping
    bad lines so a single dirty record never kills the whole analysis.
    """
    try:
        return pd.read_csv(path, encoding=encoding)
    except pd.errors.ParserError:
        # Some real-world CSVs contain extra commas inside fields.
        return pd.read_csv(
            path,
            encoding=encoding,
            error_bad_lines=False,
            warn_bad_lines=True,
        )

def normalize_column_name(name):
    """Turn a raw CSV column name into a clean, comparable key."""
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def find_column(df, field):
    """
    Locate the real DataFrame column for a logical field (e.g. 'rating').

    Returns the original column name or None when the dataset does not
    contain a matching column.
    """
    normalized = {normalize_column_name(col): col for col in df.columns}
    for alias in COLUMN_ALIASES[field]:
        if alias in normalized:
            return normalized[alias]
        # Also accept a slightly different form such as 'vote_count'
        compact = alias.replace("_", "")
        for key, value in normalized.items():
            if key.replace("_", "") == compact:
                return value
    return None


def detect_year_column(df):
    """
    If no dedicated 'year' column exists, try to derive years from a date
    column such as 'release_date'.
    """
    for col in df.columns:
        key = normalize_column_name(col)
        if "date" in key:
            dates = pd.to_datetime(df[col], errors="coerce")
            years = dates.dt.year
            if years.notna().sum() > 0:
                return col, years
    return None, None


def standardize_columns(df):
    """
    Create a DataFrame whose columns use clean snake_case names and return a
    mapping of which logical fields were found in the dataset.
    """
    df = df.copy()
    df.columns = [normalize_column_name(col) for col in df.columns]

    columns_found = {}
    for field in COLUMN_ALIASES:
        real_name = find_column(df, field)
        if real_name:
            columns_found[field] = real_name

    # Derive a year column from a date column when no year column exists.
    if "year" not in columns_found:
        date_col, years = detect_year_column(df)
        if date_col is not None:
            df["year"] = years
            columns_found["year"] = "year"

    return df, columns_found


def convert_numeric_column(df, column):
    """
    Coerce a column to numeric, turning invalid values into NaN so they can
    be handled safely. Returns (clean_series, invalid_count).
    """
    numeric = pd.to_numeric(df[column], errors="coerce")
    invalid_count = int(numeric.isna().sum() - df[column].isna().sum())
    return numeric, invalid_count


def clean_dataframe(df, columns_found):
    """
    Run the full cleaning pipeline:
      1. Keep a copy of the original shape for the report.
      2. Detect missing values.
      3. Detect duplicate rows.
      4. Remove duplicate rows.
      5. Convert numeric columns (rating, votes, popularity, year, revenue,
         runtime) to numeric types and count invalid values.
      6. Drop rows that are unusable (no title, or no rating when a rating
         column exists).

    Returns (clean_df, quality_rows) where quality_rows is a list of
    (metric, value, note) tuples used to build the data-quality report.
    """
    original_rows = len(df)
    original_cols = len(df.columns)

    quality_rows = []
    quality_rows.append(("Original rows", original_rows, "Rows in the raw CSV file"))
    quality_rows.append(("Original columns", original_cols, "Columns in the raw CSV file"))

    # --- Missing values ----------------------------------------------------
    missing_total = int(df.isna().sum().sum())
    quality_rows.append(("Missing values (total)", missing_total, "Cells with no value"))
    for col in df.columns:
        count = int(df[col].isna().sum())
        if count > 0:
            quality_rows.append(
                ("Missing values: '{}'".format(col), count, "Empty cells in this column")
            )

    # --- Duplicate rows ----------------------------------------------------
    duplicate_count = int(df.duplicated().sum())
    quality_rows.append(("Duplicate rows found", duplicate_count, "Identical rows"))
    df = df.drop_duplicates().reset_index(drop=True)
    quality_rows.append(("Duplicate rows removed", duplicate_count, "Deduplicated"))
    quality_rows.append(
        ("Rows after deduplication", len(df), "Unique rows kept")
    )

    # --- Numeric conversion ------------------------------------------------
    numeric_fields = ["rating", "votes", "popularity", "year", "revenue", "runtime"]
    for field in numeric_fields:
        if field in columns_found:
            col = columns_found[field]
            numeric, invalid = convert_numeric_column(df, col)
            df[col] = numeric
            if invalid > 0:
                quality_rows.append(
                    (
                        "Invalid values coerced: '{}'".format(col),
                        invalid,
                        "Non-numeric values turned into NaN",
                    )
                )

    # --- Drop unusable rows ------------------------------------------------
    before_drop = len(df)
    df = df.dropna(subset=[columns_found["title"]]) if "title" in columns_found else df
    if "rating" in columns_found:
        df = df[df[columns_found["rating"]].notna()]
    dropped = before_drop - len(df)
    if dropped > 0:
        quality_rows.append(
            ("Rows dropped (no title/rating)", dropped, "Rows unusable for analysis")
        )
    quality_rows.append(("Rows after cleaning", len(df), "Final clean row count"))

    return df, quality_rows


# ---------------------------------------------------------------------------
# Analytics functions
# ---------------------------------------------------------------------------


def generate_overview(df, columns_found):
    """Basic statistics about the whole dataset."""
    rating_col = columns_found.get("rating")
    rating = df[rating_col].dropna() if rating_col else pd.Series(dtype=float)

    overview = {
        "total_movies": len(df),
        "total_columns": len(df.columns),
        "title_column": columns_found.get("title"),
    }
    if rating_col is not None and len(rating) > 0:
        overview["average_rating"] = round(float(rating.mean()), 2)
        overview["median_rating"] = round(float(rating.median()), 2)
        overview["min_rating"] = float(rating.min())
        overview["max_rating"] = float(rating.max())
        overview["rating_column"] = rating_col
    return overview


def generate_top_rated(df, columns_found, top_n=10):
    """
    Identify the top-N highest-rated movies. Returns a DataFrame with the
    columns that exist in the dataset (title, rating, and votes if present).
    """
    title_col = columns_found.get("title")
    rating_col = columns_found.get("rating")
    if title_col is None or rating_col is None:
        return pd.DataFrame()

    keep_cols = [title_col, rating_col]
    for extra in ("votes", "popularity", "year"):
        if extra in columns_found and columns_found[extra] not in keep_cols:
            keep_cols.append(columns_found[extra])

    top = (
        df.dropna(subset=[title_col, rating_col])
        .sort_values(by=rating_col, ascending=False)
        .head(top_n)
        .loc[:, keep_cols]
        .reset_index(drop=True)
    )
    return top


def generate_genre_analysis(df, columns_found, top_n=10):
    """
    Compute movie counts and average ratings per genre, sorted by count.
    Returns (genre_count_df, genre_rating_df).
    """
    genre_col = columns_found.get("genres")
    if genre_col is None:
        return pd.DataFrame(), pd.DataFrame()

    # Split 'Action, Adventure' style cells so each movie counts once per
    # genre, then use DataFrame.explode to un-nest the list column safely.
    genre_df = df.copy()
    genre_df["_genre"] = genre_df[genre_col].fillna("").astype(str).str.split(r"[,|;]")
    genre_df = genre_df.explode("_genre").reset_index(drop=True)
    genre_df["_genre"] = genre_df["_genre"].str.strip()

    genre_count = (
        genre_df[genre_df["_genre"] != ""]
        .groupby("_genre")
        .size()
        .reset_index(name="movie_count")
        .sort_values("movie_count", ascending=False)
        .reset_index(drop=True)
    )
    genre_count.columns = ["genre", "movie_count"]

    rating_col = columns_found.get("rating")
    if rating_col is not None:
        genre_rating = (
            genre_df[genre_df["_genre"] != ""]
            .groupby("_genre")[rating_col]
            .mean()
            .round(2)
            .reset_index(name="average_rating")
            .sort_values("average_rating", ascending=False)
            .reset_index(drop=True)
        )
        genre_rating.columns = ["genre", "average_rating"]
    else:
        genre_rating = pd.DataFrame()

    return genre_count.head(top_n), genre_rating.head(top_n)


def generate_popularity_analysis(df, columns_found, top_n=10):
    """Most popular movies, plus the relationship between popularity and rating."""
    title_col = columns_found.get("title")
    pop_col = columns_found.get("popularity")
    if title_col is None or pop_col is None:
        return {}

    keep_cols = [title_col, pop_col]
    if "rating" in columns_found:
        keep_cols.append(columns_found["rating"])

    most_popular = (
        df.dropna(subset=[title_col, pop_col])
        .sort_values(by=pop_col, ascending=False)
        .head(top_n)
        .loc[:, keep_cols]
        .reset_index(drop=True)
    )

    result = {"most_popular": most_popular, "popularity_column": pop_col}
    if "rating" in columns_found:
        valid = df[[pop_col, columns_found["rating"]]].dropna()
        if len(valid) > 1:
            corr = np.corrcoef(valid[pop_col], valid[columns_found["rating"]])[0, 1]
            result["popularity_rating_correlation"] = round(float(corr), 3)
    return result


def generate_vote_analysis(df, columns_found, top_n=10):
    """Most-voted movies, plus the relationship between votes and rating."""
    title_col = columns_found.get("title")
    vote_col = columns_found.get("votes")
    if title_col is None or vote_col is None:
        return {}

    keep_cols = [title_col, vote_col]
    if "rating" in columns_found:
        keep_cols.append(columns_found["rating"])

    most_voted = (
        df.dropna(subset=[title_col, vote_col])
        .sort_values(by=vote_col, ascending=False)
        .head(top_n)
        .loc[:, keep_cols]
        .reset_index(drop=True)
    )

    result = {"most_voted": most_voted, "votes_column": vote_col}
    if "rating" in columns_found:
        valid = df[[vote_col, columns_found["rating"]]].dropna()
        if len(valid) > 1:
            corr = np.corrcoef(valid[vote_col], valid[columns_found["rating"]])[0, 1]
            result["votes_rating_correlation"] = round(float(corr), 3)
    return result


def generate_release_trend(df, columns_found, top_n=10):
    """Number of movies released per year and the busiest years."""
    year_col = columns_found.get("year")
    if year_col is None:
        return pd.DataFrame()

    valid = df[df[year_col].notna()].copy()
    valid[year_col] = valid[year_col].astype(int)

    trend = (
        valid.groupby(year_col)
        .size()
        .reset_index(name="movie_count")
        .sort_values(year_col)
        .reset_index(drop=True)
    )
    trend.columns = ["year", "movie_count"]
    return trend


def generate_rating_analysis(df, columns_found):
    """
    Rating distribution: average rating plus the most common rating range.
    The rating range uses 1-point buckets (e.g. 7.0 - 8.0).
    """
    rating_col = columns_found.get("rating")
    if rating_col is None:
        return {}

    rating = df[rating_col].dropna()
    if rating.empty:
        return {}

    bins = list(range(int(np.floor(rating.min())), int(np.ceil(rating.max())) + 2))
    if len(bins) < 2:
        bins = [int(np.floor(rating.min())), int(np.ceil(rating.max()))]

    buckets = pd.cut(rating, bins=bins, right=False)
    bucket_counts = buckets.value_counts().sort_index()

    # Human-readable label of the most common bucket, e.g. '7.0 - 8.0'.
    top_bucket = bucket_counts.idxmax()
    common_range = "{} - {}".format(top_bucket.left, top_bucket.right)

    return {
        "average_rating": round(float(rating.mean()), 2),
        "count": int(rating.count()),
        "distribution": [
            {
                "range": "{} - {}".format(interval.left, interval.right),
                "count": int(count),
            }
            for interval, count in bucket_counts.items()
        ],
        "most_common_range": common_range,
        "most_common_range_count": int(bucket_counts.max()),
    }


# ---------------------------------------------------------------------------
# Chart generation
# ---------------------------------------------------------------------------


def make_chart_filename(name):
    """Return the full output path for a chart PNG."""
    return CHART_DIR / "{}.png".format(name)


def save_chart(fig, filename):
    """Save a figure at high resolution and close it to free memory."""
    fig.savefig(make_chart_filename(filename), dpi=150, bbox_inches="tight")
    plt.close(fig)


def chart_rating_distribution(df, columns_found):
    """Histogram of the movie rating distribution."""
    rating_col = columns_found.get("rating")
    if rating_col is None:
        return None
    rating = df[rating_col].dropna()
    if rating.empty:
        return None

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.histplot(rating, bins=20, kde=True, color="#4C72B0", ax=ax)
    ax.axvline(
        rating.mean(),
        color="#C44E52",
        linestyle="--",
        linewidth=2,
        label="Mean = {:.2f}".format(rating.mean()),
    )
    ax.set_title("Rating Distribution")
    ax.set_xlabel("Rating")
    ax.set_ylabel("Number of Movies")
    ax.legend()
    save_chart(fig, "rating_distribution")
    return "rating_distribution.png"


def chart_top_rated(df, columns_found):
    """Horizontal bar chart of the top 10 highest-rated movies."""
    top = generate_top_rated(df, columns_found, top_n=10)
    title_col = columns_found.get("title")
    rating_col = columns_found.get("rating")
    if top.empty:
        return None

    fig, ax = plt.subplots(figsize=(9, 6))
    top_sorted = top.sort_values(rating_col)
    y_pos = range(len(top_sorted))
    bars = ax.barh(y_pos, top_sorted[rating_col], color="#55A868")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(top_sorted[title_col].astype(str))
    ax.set_xlabel("Rating")
    ax.set_title("Top 10 Highest-Rated Movies")
    for bar, value in zip(bars, top_sorted[rating_col]):
        ax.text(
            value + 0.05,
            bar.get_y() + bar.get_height() / 2,
            "{:.1f}".format(value),
            va="center",
            fontsize=9,
        )
    save_chart(fig, "top_rated_movies")
    return "top_rated_movies.png"


def chart_popular_genres(genre_count_df):
    """Bar chart of the top 10 most common genres."""
    if genre_count_df.empty:
        return None

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(
        data=genre_count_df,
        x="movie_count",
        y="genre",
        palette="viridis",
        ax=ax,
    )
    ax.set_title("Top 10 Most Popular Genres")
    ax.set_xlabel("Number of Movies")
    ax.set_ylabel("Genre")
    save_chart(fig, "popular_genres")
    return "popular_genres.png"


def chart_genre_average_rating(genre_rating_df):
    """Bar chart of average rating by genre."""
    if genre_rating_df.empty:
        return None

    fig, ax = plt.subplots(figsize=(9, 5))
    sns.barplot(
        data=genre_rating_df,
        x="average_rating",
        y="genre",
        palette="rocket_r",
        ax=ax,
    )
    ax.set_title("Average Rating by Genre (Top Genres)")
    ax.set_xlabel("Average Rating")
    ax.set_ylabel("Genre")
    save_chart(fig, "genre_average_rating")
    return "genre_average_rating.png"


def chart_release_trend(trend_df):
    """Line chart of the number of movies released per year."""
    if trend_df.empty:
        return None

    fig, ax = plt.subplots(figsize=(10, 5))
    sns.lineplot(data=trend_df, x="year", y="movie_count", marker="o", ax=ax)
    ax.set_title("Movies Released by Year")
    ax.set_xlabel("Year")
    ax.set_ylabel("Number of Movies")

    peak_year = trend_df.loc[trend_df["movie_count"].idxmax(), "year"]
    ax.axvline(
        peak_year,
        color="#C44E52",
        linestyle="--",
        linewidth=2,
        label="Peak: {} ({} movies)".format(
            peak_year, trend_df["movie_count"].max()
        ),
    )
    ax.legend()
    save_chart(fig, "release_trend")
    return "release_trend.png"


def chart_rating_vs_popularity(df, columns_found):
    """Scatter plot of rating versus popularity with a trend line."""
    rating_col = columns_found.get("rating")
    pop_col = columns_found.get("popularity")
    if rating_col is None or pop_col is None:
        return None

    valid = df[[rating_col, pop_col]].dropna()
    if len(valid) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.scatterplot(data=valid, x=rating_col, y=pop_col, alpha=0.7, ax=ax)
    sns.regplot(
        data=valid,
        x=rating_col,
        y=pop_col,
        scatter=False,
        color="#C44E52",
        ax=ax,
    )
    ax.set_title("Rating vs Popularity")
    ax.set_xlabel("Rating")
    ax.set_ylabel("Popularity")
    save_chart(fig, "rating_vs_popularity")
    return "rating_vs_popularity.png"


def chart_rating_vs_votes(df, columns_found):
    """Scatter plot of rating versus vote count, when votes exist."""
    rating_col = columns_found.get("rating")
    vote_col = columns_found.get("votes")
    if rating_col is None or vote_col is None:
        return None

    valid = df[[rating_col, vote_col]].dropna()
    if len(valid) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 5))
    sns.scatterplot(data=valid, x=rating_col, y=vote_col, alpha=0.7, ax=ax)
    sns.regplot(
        data=valid,
        x=rating_col,
        y=vote_col,
        scatter=False,
        color="#8172B2",
        ax=ax,
    )
    ax.set_title("Rating vs Vote Count")
    ax.set_xlabel("Rating")
    ax.set_ylabel("Vote Count")
    save_chart(fig, "rating_vs_votes")
    return "rating_vs_votes.png"


def generate_all_charts(df, columns_found, results):
    """Create every chart that the dataset supports. Returns chart filenames."""
    charts = []

    chart = chart_rating_distribution(df, columns_found)
    if chart:
        charts.append(chart)

    chart = chart_top_rated(df, columns_found)
    if chart:
        charts.append(chart)

    genre_count, genre_rating = generate_genre_analysis(df, columns_found)
    results["genres"] = {"count": genre_count, "rating": genre_rating}

    chart = chart_popular_genres(genre_count)
    if chart:
        charts.append(chart)

    chart = chart_genre_average_rating(genre_rating)
    if chart:
        charts.append(chart)

    chart = chart_release_trend(results.get("release_trend"))
    if chart:
        charts.append(chart)

    chart = chart_rating_vs_popularity(df, columns_found)
    if chart:
        charts.append(chart)

    chart = chart_rating_vs_votes(df, columns_found)
    if chart:
        charts.append(chart)

    return charts


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def describe_correlation(value):
    """Turn a correlation coefficient into plain English."""
    if value is None:
        return "not enough data to describe"
    if abs(value) < 0.2:
        return "little or no linear relationship"
    if value > 0:
        return "a positive relationship (as one goes up, so does the other)"
    return "a negative relationship (as one goes up, the other goes down)"


def generate_insights(df, columns_found, results):
    """Create human-readable insights strictly from the real dataset."""
    insights = []
    overview = results["overview"]

    if "average_rating" in overview:
        insights.append(
            "The average movie rating is {}.".format(overview["average_rating"])
        )
        insights.append(
            "The median rating is {} and ratings range from {} to {}.".format(
                overview["median_rating"],
                overview["min_rating"],
                overview["max_rating"],
            )
        )

    rating_analysis = results.get("rating_analysis", {})
    if rating_analysis.get("most_common_range"):
        insights.append(
            "The most common rating range is {} ({} movies).".format(
                rating_analysis["most_common_range"],
                rating_analysis["most_common_range_count"],
            )
        )

    genre_info = results.get("genres", {})
    genre_count = genre_info.get("count", pd.DataFrame())
    if not genre_count.empty:
        top_genre = genre_count.iloc[0]
        insights.append(
            "The most common genre is '{}' with {} movies.".format(
                top_genre["genre"], top_genre["movie_count"]
            )
        )

    top_rated = results.get("top_rated")
    if top_rated is not None and not top_rated.empty:
        title_col = columns_found["title"]
        rating_col = columns_found["rating"]
        highest = top_rated.iloc[0]
        insights.append(
            "'{}' is the highest-rated movie with a rating of {}.".format(
                highest[title_col], highest[rating_col]
            )
        )

    trend = results.get("release_trend")
    if trend is not None and not trend.empty:
        peak = trend.loc[trend["movie_count"].idxmax()]
        insights.append(
            "The year {} had the highest number of movie releases ({} movies).".format(
                peak["year"], peak["movie_count"]
            )
        )

    popularity = results.get("popularity", {})
    if popularity.get("popularity_rating_correlation") is not None:
        corr = popularity["popularity_rating_correlation"]
        insights.append(
            "Movies with higher ratings tend to have {} with popularity "
            "(correlation = {}).".format(describe_correlation(corr), corr)
        )

    votes = results.get("votes", {})
    if votes.get("votes_rating_correlation") is not None:
        corr = votes["votes_rating_correlation"]
        insights.append(
            "Vote count and rating show {} (correlation = {}).".format(
                describe_correlation(corr), corr
            )
        )
    if votes.get("most_voted") is not None and not votes["most_voted"].empty:
        title_col = columns_found["title"]
        vote_col = columns_found["votes"]
        most = votes["most_voted"].iloc[0]
        insights.append(
            "'{}' is the most-voted movie with {} votes.".format(
                most[title_col], most[vote_col]
            )
        )

    return insights


# ---------------------------------------------------------------------------
# Reports & export
# ---------------------------------------------------------------------------


def export_reports(results, quality_rows):
    """Write all CSV + text reports and return the list of file names."""
    reports = []

    # 1. Data-quality report.
    quality_df = pd.DataFrame(quality_rows, columns=["Metric", "Value", "Note"])
    quality_path = REPORT_DIR / "data_quality_report.csv"
    quality_df.to_csv(quality_path, index=False)
    reports.append(quality_path.name)

    # 2. Top-rated movies.
    top_rated = results.get("top_rated")
    if top_rated is not None and not top_rated.empty:
        path = REPORT_DIR / "top_rated_movies.csv"
        top_rated.to_csv(path, index=False)
        reports.append(path.name)

    genre_info = results.get("genres", {})
    genre_count = genre_info.get("count", pd.DataFrame())

    # 3. Popular genres (movie counts).
    if not genre_count.empty:
        path = REPORT_DIR / "popular_genres.csv"
        genre_count.to_csv(path, index=False)
        reports.append(path.name)

    # 4. Genre analysis (counts + average rating combined).
    genre_rating = genre_info.get("rating", pd.DataFrame())
    if not genre_count.empty:
        genre_analysis = genre_count
        if not genre_rating.empty:
            genre_analysis = genre_count.merge(
                genre_rating, on="genre", how="left"
            )
        path = REPORT_DIR / "genre_analysis.csv"
        genre_analysis.to_csv(path, index=False)
        reports.append(path.name)

    # 5. Human-readable summary.
    summary_path = REPORT_DIR / "movie_analysis_summary.txt"
    with open(str(summary_path), "w", encoding="utf-8") as handle:
        handle.write(build_summary_text(results))
    reports.append(summary_path.name)

    return reports


def build_summary_text(results):
    """Build the plain-text analysis summary shown in the terminal and saved."""
    lines = []
    lines.append("=" * 62)
    lines.append("MOVIE DATA ANALYTICS SUMMARY")
    lines.append("=" * 62)

    overview = results["overview"]
    lines.append("\nOVERVIEW")
    lines.append("-" * 62)
    lines.append("  Total movies        : {}".format(overview["total_movies"]))
    lines.append("  Total columns       : {}".format(overview["total_columns"]))
    if "average_rating" in overview:
        lines.append("  Average rating      : {}".format(overview["average_rating"]))
        lines.append("  Median rating       : {}".format(overview["median_rating"]))
        lines.append("  Minimum rating      : {}".format(overview["min_rating"]))
        lines.append("  Maximum rating      : {}".format(overview["max_rating"]))

    rating_analysis = results.get("rating_analysis", {})
    if rating_analysis.get("most_common_range"):
        lines.append("\nRATING DISTRIBUTION")
        lines.append("-" * 62)
        lines.append("  Most common range   : {}".format(rating_analysis["most_common_range"]))
        lines.append("  Movies in that range: {}".format(rating_analysis["most_common_range_count"]))

    top_rated = results.get("top_rated")
    if top_rated is not None and not top_rated.empty:
        lines.append("\nTOP-RATED MOVIES")
        lines.append("-" * 62)
        for i, row in top_rated.iterrows():
            lines.append("  {:<3} {} -> {}".format(i + 1, row[0], row[1]))

    genre_info = results.get("genres", {})
    genre_count = genre_info.get("count", pd.DataFrame())
    if not genre_count.empty:
        lines.append("\nTOP 10 GENRES")
        lines.append("-" * 62)
        for i, row in genre_count.iterrows():
            lines.append("  {:<3} {:<20} {} movies".format(i + 1, row["genre"], row["movie_count"]))

    trend = results.get("release_trend")
    if trend is not None and not trend.empty:
        lines.append("\nRELEASE TREND")
        lines.append("-" * 62)
        lines.append("  Range of years      : {} - {}".format(trend["year"].min(), trend["year"].max()))
        peak = trend.loc[trend["movie_count"].idxmax()]
        lines.append("  Busiest year        : {} ({} movies)".format(peak["year"], peak["movie_count"]))

    insights = results.get("insights", [])
    if insights:
        lines.append("\nAUTOMATIC INSIGHTS")
        lines.append("-" * 62)
        for insight in insights:
            lines.append("  - " + insight)

    lines.append("\n" + "=" * 62)
    lines.append("Charts saved to  : output/charts/")
    lines.append("Reports saved to : output/reports/")
    lines.append("=" * 62)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

# Output directories (created lazily so imports never fail).
PROJECT_ROOT = Path(__file__).resolve().parent
CHART_DIR = PROJECT_ROOT / "output" / "charts"
REPORT_DIR = PROJECT_ROOT / "output" / "reports"


def ensure_output_dirs():
    """Make sure the output folders exist."""
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)


def run_analysis(csv_path="data/movies.csv"):
    """
    Run the full pipeline on any CSV file.

    Returns a dictionary containing every result: overview, top-rated,
    genre stats, popularity, votes, release trend, rating analysis,
    insights, chart filenames, report filenames, detected columns and the
    cleaned DataFrame. Raises on missing file or unreadable CSV.
    """
    ensure_output_dirs()

    # 1. Load
    df = load_csv(csv_path)

    # 2. Standardize columns and detect which logical fields exist.
    df, columns_found = standardize_columns(df)

    # 3. Clean.
    df, quality_rows = clean_dataframe(df, columns_found)

    # 4. Analytics.
    results = {
        "columns_found": columns_found,
        "cleaned_dataframe": df,
        "overview": generate_overview(df, columns_found),
        "top_rated": generate_top_rated(df, columns_found),
        "release_trend": generate_release_trend(df, columns_found),
        "rating_analysis": generate_rating_analysis(df, columns_found),
    }

    # Charts fill in the genre results too.
    charts = generate_all_charts(df, columns_found, results)
    results["charts"] = charts

    results["popularity"] = generate_popularity_analysis(df, columns_found)
    results["votes"] = generate_vote_analysis(df, columns_found)

    # 5. Insights (from real data only).
    results["insights"] = generate_insights(df, columns_found, results)

    # 6. Reports.
    results["reports"] = export_reports(results, quality_rows)

    return results


def main():
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze a movie CSV dataset and produce charts + reports."
    )
    parser.add_argument(
        "csv_path",
        nargs="?",
        default="data/movies.csv",
        help="Path to the movie CSV file (default: data/movies.csv)",
    )
    args = parser.parse_args()

    try:
        results = run_analysis(args.csv_path)
    except FileNotFoundError as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)
    except ValueError as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        sys.exit(1)

    print(build_summary_text(results))
    print("\nCharts generated: {}".format(len(results["charts"])))
    print("Reports generated: {}".format(len(results["reports"])))
    print("\nDone. Analysis complete.")


if __name__ == "__main__":
    main()
