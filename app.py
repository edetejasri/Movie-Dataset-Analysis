"""
Movie Data Analytics Platform - Flask Backend
=============================================

Serves the interactive Movie Analytics Dashboard and exposes a JSON API so
the frontend can show live statistics, top-rated movies, genre stats and
charts. Users can upload their own CSV file and the whole analysis re-runs
against it.

Run with:
    python app.py
Then open http://127.0.0.1:5000 in your browser.

API endpoints
-------------
GET  /                     -> the dashboard (HTML)
GET  /api/stats            -> overview statistics (KPI cards)
GET  /api/top-rated        -> top 10 highest-rated movies
GET  /api/genres           -> genre counts + average rating by genre
GET  /api/analytics        -> charts list, insights, trends, correlations
GET  /api/movies           -> searchable/filterable movie list (?q=, &genre=, &min_rating=, &max_rating=)
POST /api/upload           -> upload your own CSV (multipart field "file")
POST /api/reset            -> switch back to the bundled sample dataset
GET  /output/charts/<name> -> a generated chart PNG
GET  /output/reports/<name>-> a generated report file
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Flask, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

import movie_analytics as ma

app = Flask(__name__)

# Reasonable upload limit (25 MB) to keep the server responsive.
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {"csv"}

DEFAULT_CSV_PATH = str(ma.PROJECT_ROOT / "data" / "movies.csv")
UPLOAD_DIR = ma.PROJECT_ROOT / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Application state: which CSV is loaded and its cached analysis results.
state = {"csv_path": DEFAULT_CSV_PATH, "results": None, "filename": "movies.csv"}


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------


def make_json_safe(value):
    """Recursively convert numpy / pandas values into plain JSON types."""
    if isinstance(value, pd.DataFrame):
        return make_json_safe(value.replace({np.nan: None}).to_dict(orient="records"))
    if isinstance(value, pd.Series):
        return make_json_safe(value.replace({np.nan: None}).to_dict())
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.ndarray):
        return make_json_safe(value.tolist())
    if isinstance(value, pd.Timestamp):
        return str(value)
    return value


def df_to_records(dataframe):
    """Convert a DataFrame into a list of dicts with NaN replaced by None."""
    if dataframe is None or dataframe.empty:
        return []
    return make_json_safe(dataframe.replace({np.nan: None}).to_dict(orient="records"))


# ---------------------------------------------------------------------------
# Analysis state
# ---------------------------------------------------------------------------


def get_results():
    """Return cached results, running the analysis on first call."""
    if state["results"] is None:
        state["results"] = ma.run_analysis(state["csv_path"])
    return state["results"]


def reload_analysis(csv_path, display_name=None):
    """Re-run the whole pipeline against a new CSV and cache the results."""
    state["csv_path"] = csv_path
    state["filename"] = display_name or Path(csv_path).name
    state["results"] = ma.run_analysis(csv_path)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Render the dashboard page."""
    return render_template("index.html")


# ---------------------------------------------------------------------------
# API: statistics
# ---------------------------------------------------------------------------


@app.route("/api/stats")
def api_stats():
    """Overview statistics used by the KPI cards."""
    try:
        results = get_results()
        overview = results["overview"]
        columns = results["columns_found"]
        genres = results.get("genres", {}).get("count", pd.DataFrame())
        most_popular_genre = (
            genres.iloc[0]["genre"] if not genres.empty else "n/a"
        )

        return jsonify(
            {
                "total_movies": overview["total_movies"],
                "average_rating": overview.get("average_rating"),
                "highest_rating": overview.get("max_rating"),
                "most_popular_genre": most_popular_genre,
                "median_rating": overview.get("median_rating"),
                "lowest_rating": overview.get("min_rating"),
                "columns_found": columns,
                "total_columns": overview["total_columns"],
                "dataset_name": state["filename"],
            }
        )
    except Exception as error:  # noqa: BLE001 - return a clean error message
        return jsonify({"error": str(error)}), 500


@app.route("/api/top-rated")
def api_top_rated():
    """Top 10 highest-rated movies."""
    try:
        results = get_results()
        columns = results["columns_found"]
        records = []
        for row in df_to_records(results.get("top_rated")):
            title = row.get(columns["title"]) if "title" in columns else "n/a"
            rating = row.get(columns.get("rating"))
            records.append(
                {
                    "title": title,
                    "rating": rating,
                    "votes": row.get(columns.get("votes")),
                    "popularity": row.get(columns.get("popularity")),
                    "year": row.get(columns.get("year")),
                }
            )
        return jsonify({"top_rated": records})
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": str(error)}), 500


@app.route("/api/genres")
def api_genres():
    """Genre counts and average rating by genre."""
    try:
        results = get_results()
        genre_info = results.get("genres", {})
        count_records = df_to_records(genre_info.get("count"))
        rating_records = df_to_records(genre_info.get("rating"))

        rating_by_genre = {item["genre"]: item["average_rating"] for item in rating_records}
        for item in count_records:
            item["average_rating"] = rating_by_genre.get(item["genre"])

        return jsonify({"genres": count_records})
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": str(error)}), 500


@app.route("/api/analytics")
def api_analytics():
    """Charts, insights, trends and relationships between columns."""
    try:
        results = get_results()
        columns = results["columns_found"]
        return jsonify(
            {
                "charts": results.get("charts", []),
                "insights": results.get("insights", []),
                "rating_analysis": make_json_safe(results.get("rating_analysis", {})),
                "release_trend": df_to_records(results.get("release_trend")),
                "popularity": make_json_safe(results.get("popularity", {})),
                "votes": make_json_safe(results.get("votes", {})),
                "columns_found": columns,
                "dataset_name": state["filename"],
            }
        )
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": str(error)}), 500


@app.route("/api/movies")
def api_movies():
    """
    Searchable and filterable movie list.

    Query parameters (all optional):
      q          -> text search on the movie title
      genre      -> keep movies whose genre list contains this text
      min_rating -> only movies with rating >= this value
      max_rating -> only movies with rating <= this value
      limit      -> maximum number of rows to return
    """
    try:
        results = get_results()
        df = results["cleaned_dataframe"].copy()
        columns = results["columns_found"]

        query = (request.args.get("q") or "").strip().lower()
        genre = (request.args.get("genre") or "").strip().lower()
        min_rating = request.args.get("min_rating", type=float)
        max_rating = request.args.get("max_rating", type=float)

        title_col = columns.get("title")
        if title_col and query:
            df = df[df[title_col].astype(str).str.lower().str.contains(query, na=False)]

        genre_col = columns.get("genres")
        if genre_col and genre:
            df = df[df[genre_col].astype(str).str.lower().str.contains(genre, na=False)]

        rating_col = columns.get("rating")
        if rating_col:
            if min_rating is not None:
                df = df[df[rating_col] >= min_rating]
            if max_rating is not None:
                df = df[df[rating_col] <= max_rating]

        limit = request.args.get("limit", default=200, type=int)
        df = df.head(limit)

        records = []
        for row in df_to_records(df):
            records.append(
                {
                    "title": row.get(columns.get("title")),
                    "rating": row.get(columns.get("rating")),
                    "genres": row.get(columns.get("genres")),
                    "year": row.get(columns.get("year")),
                    "popularity": row.get(columns.get("popularity")),
                    "votes": row.get(columns.get("votes")),
                }
            )
        return jsonify({"movies": records, "count": len(records)})
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": str(error)}), 500


# ---------------------------------------------------------------------------
# API: upload / reset
# ---------------------------------------------------------------------------


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Accept a user CSV, re-run the analysis and refresh every endpoint."""
    file = request.files.get("file")
    if file is None or file.filename == "":
        return jsonify({"error": "No file provided (field name must be 'file')."}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Only .csv files are allowed."}), 400

    safe_name = secure_filename(file.filename) or "uploaded_movies.csv"
    destination = UPLOAD_DIR / safe_name
    file.save(str(destination))

    try:
        reload_analysis(str(destination), display_name=safe_name)
        return jsonify(
            {
                "message": "Dataset '{}' loaded and analyzed.".format(safe_name),
                "filename": safe_name,
            }
        )
    except Exception as error:  # noqa: BLE001
        return jsonify({"error": "Analysis failed: {}".format(error)}), 500


@app.route("/api/reset", methods=["POST"])
def api_reset():
    """Switch back to the bundled sample dataset."""
    reload_analysis(DEFAULT_CSV_PATH, display_name="movies.csv")
    return jsonify({"message": "Switched back to the sample dataset."})


# ---------------------------------------------------------------------------
# Static generated files
# ---------------------------------------------------------------------------


@app.route("/output/charts/<path:filename>")
def serve_chart(filename):
    return send_from_directory(str(ma.CHART_DIR), filename)


@app.route("/output/reports/<path:filename>")
def serve_report(filename):
    return send_from_directory(str(ma.REPORT_DIR), filename)


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(str(UPLOAD_DIR), filename)


# ---------------------------------------------------------------------------
# Error handler for uploads that are too large
# ---------------------------------------------------------------------------


@app.errorhandler(413)
def too_large(error):
    return jsonify({"error": "File too large. Maximum allowed size is 25 MB."}), 413


if __name__ == "__main__":
    # host='127.0.0.1' keeps the server local; use '0.0.0.0' to allow
    # access from other devices on your network.
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
