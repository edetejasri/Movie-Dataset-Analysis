# Movie Data Analytics Platform

A beginner-friendly, professional **Python movie dataset analysis system**.
Feed it any CSV containing movie information and it will:

- **Clean** the data automatically (missing values, duplicates, bad numbers).
- **Analyze** ratings, genres, popularity, votes and release trends.
- **Visualize** the results with professional Matplotlib + Seaborn charts.
- **Report** everything as CSV files and a human-readable summary.
- **Serve** an interactive **Movie Analytics Dashboard** with a Flask backend.

The application **detects the available columns automatically**. It only runs
the analyses your dataset actually supports, and it works with **your own CSV**
— nothing is hard-coded.

---

## Features

| Area | What it does |
| --- | --- |
| Data cleaning | Standardizes column names, detects & removes duplicates, converts numeric columns, handles invalid values, drops unusable rows |
| Overview | Total movies, columns, average / median / min / max rating |
| Top-rated | Top 10 highest-rated movies |
| Genre analysis | Movie count per genre + average rating per genre |
| Popularity | Most popular movies, correlation between popularity and rating |
| Votes | Most-voted movies, correlation between votes and rating |
| Release trend | Movies released per year, busiest production years |
| Rating analysis | Rating distribution and the most common rating range |
| Charts | 7 charts saved as high-resolution PNGs in `output/charts/` |
| Reports | Data-quality report, top-rated CSV, genre CSVs, text summary |
| Dashboard | Responsive web UI with KPI cards, charts, search, filters & CSV upload |
| API | JSON endpoints for stats, top-rated, genres, analytics, movies, upload |

---

## Project Structure

```
movie-data-analytics/
│
├── data/
│   └── movies.csv                 # sample dataset (replace with your own)
│
├── output/                        # generated when you run the analysis
│   ├── charts/                    #     .png charts (high resolution)
│   │   ├── rating_distribution.png
│   │   ├── top_rated_movies.png
│   │   ├── popular_genres.png
│   │   ├── genre_average_rating.png
│   │   ├── release_trend.png
│   │   ├── rating_vs_popularity.png
│   │   └── rating_vs_votes.png
│   │
│   └── reports/
│       ├── top_rated_movies.csv
│       ├── popular_genres.csv
│       ├── genre_analysis.csv
│       ├── data_quality_report.csv
│       └── movie_analysis_summary.txt
│
├── templates/
│   └── index.html                 # dashboard page
├── static/
│   ├── css/style.css              # dashboard styles
│   └── js/app.js                  # dashboard logic
├── uploads/                       # user-uploaded CSVs are stored here
│
├── movie_analytics.py             # core engine (cleaning + analytics + charts)
├── app.py                         # Flask backend / REST API
├── requirements.txt
└── README.md
```

---

## Installation

> Python 3.6+ is required. A virtual environment is recommended.

```bash
# 1. Go into the project folder
cd movie-data-analytics

# 2. (Recommended) create a virtual environment
python -m venv venv

# 3. Activate it
#    Windows (PowerShell):
venv\Scripts\Activate.ps1
#    Windows (Command Prompt):
venv\Scripts\activate.bat
#    macOS / Linux:
source venv/bin/activate

# 4. Install the dependencies
pip install -r requirements.txt
```

> On Python 3.8+ you may prefer the latest library versions:
> `pip install pandas numpy matplotlib seaborn flask`

---

## Run Commands

### 1) Run the analysis from the command line

```bash
# Use the bundled sample dataset
python movie_analytics.py

# Use your own dataset
python movie_analytics.py path/to/your_movies.csv
```

This prints a summary to the terminal and writes:

- Charts to `output/charts/*.png`
- Reports to `output/reports/*`

### 2) Run the interactive dashboard

```bash
python app.py
```

Open your browser at **http://127.0.0.1:5000**

- Upload your own CSV from the dashboard (it re-runs the full analysis).
- Search movies, filter by genre and rating range.
- Reset to the sample dataset with one click.

---

## Example CSV Format

Plain CSV with a header row. Column names are detected flexibly — the ones
below are examples, not requirements.

```csv
title,genre,rating,votes,popularity,year,runtime,revenue
The Dark Knight,Action|Crime|Drama,9.0,2500000,88.4,2008,152,1005000000
Inception,Sci-Fi|Action|Thriller,8.8,2300000,85.2,2010,148,829000000
Interstellar,Sci-Fi|Drama|Adventure,8.6,1800000,80.7,2014,169,677000000
```

Accepted column aliases (auto-detected):

| Logical field | Recognized column names |
| --- | --- |
| Title | `title`, `name`, `movie_title`, `film`, `movie` |
| Genre | `genre`, `genres` (multiple genres separated by `,` `|` or `;`) |
| Rating | `rating`, `score`, `vote_average`, `average_rating`, `imdb_rating` |
| Votes | `votes`, `vote_count`, `num_votes`, `imdb_votes` |
| Popularity | `popularity` |
| Year | `year`, `release_year`, `year_of_release` (or a `release_date` column) |
| Revenue | `revenue`, `gross`, `box_office` |
| Runtime | `runtime`, `duration`, `length` |

> Only include the columns you have. Everything is optional except that at
> least a title (or a rating) column makes the analysis meaningful.

---

## How the Analysis Works

The pipeline lives in `movie_analytics.py` and runs in six steps:

1. **Load** — the CSV is read safely (multiple encodings, malformed rows
   are skipped instead of crashing the run). Missing files raise a clear error.
2. **Standardize** — column names are normalized to lowercase snake_case and
   matched against a table of aliases so `Score`, `vote_count` or
   `Release_Year` are all recognized. If only a date column exists, years are
   derived from it.
3. **Clean** — missing values are counted, duplicate rows are removed, numeric
   columns are converted (invalid values become NaN and are counted), and rows
   without a title or rating are dropped. Every step is recorded in
   `output/reports/data_quality_report.csv`.
4. **Analyze** — small, single-purpose functions compute the overview, top
   rated movies, genre counts/average ratings (multi-genre cells are split),
   popularity vs rating correlation, votes vs rating correlation, release
   trend and the rating distribution.
5. **Visualize** — each chart is drawn with Matplotlib + Seaborn, given a
   meaningful title, axis labels and readable fonts, then saved at
   **150 DPI** into `output/charts/`.
6. **Report & insight** — the script writes CSV reports and a text summary,
   and generates plain-English insights such as *"The most common genre is
   Drama with 37 movies."* All insights come **only from the real dataset**.

---

## Connecting the Frontend to the Python Backend

The dashboard is plain HTML/CSS/JavaScript served by Flask. The frontend
**never touches the data directly** — it talks to the backend through a
REST/JSON API:

1. Flask serves the page at `/` (`templates/index.html`).
2. When the page loads, `static/js/app.js` calls these endpoints in parallel:
   - `GET /api/stats` → fills the KPI cards.
   - `GET /api/top-rated` → fills the "Top 10 Highest-Rated Movies" table.
   - `GET /api/genres` → fills the "Popular Genres" bars + genre dropdown.
   - `GET /api/analytics` → renders the charts (`<img src="/output/charts/…">`),
     the automatic insights and the trend data.
3. Search / genre / rating filters call `GET /api/movies?q=…&genre=…&min_rating=…&max_rating=…`.
4. The **CSV upload** form posts to `POST /api/upload`, the backend re-runs
   `run_analysis()` against the uploaded file, and the frontend reloads all
   panels automatically.
5. `POST /api/reset` switches back to the bundled sample dataset.

### API Reference

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/` | Dashboard page (HTML) |
| GET | `/api/stats` | Overview statistics for KPI cards |
| GET | `/api/top-rated` | Top 10 highest-rated movies |
| GET | `/api/genres` | Genre counts + average ratings |
| GET | `/api/analytics` | Charts list, insights, trends, correlations |
| GET | `/api/movies` | Searchable/filterable movie list |
| POST | `/api/upload` | Upload your own CSV (field name: `file`) |
| POST | `/api/reset` | Reload the sample dataset |
| GET | `/output/charts/<name>` | Serve a generated chart PNG |
| GET | `/output/reports/<name>` | Serve a generated report file |

All API endpoints return JSON.

---

## GitHub

Repository: https://github.com/edetejasri/Movie-Dataset-Analysis

To push your changes to GitHub:

```bash
git init
git add .
git commit -m "Add Movie Data Analytics Platform"
git branch -M main
git remote add origin https://github.com/edetejasri/Movie-Dataset-Analysis.git
git push -u origin main
```

---

## License

Free to use for learning and experimentation.
