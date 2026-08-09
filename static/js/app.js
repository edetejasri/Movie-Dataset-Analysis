/* ==========================================================================
   Movie Analytics Dashboard - Frontend logic
   Fetches data from the Flask API and renders KPI cards, charts, insights,
   genre bars, and a searchable/filterable movie table.
   ========================================================================== */

"use strict";

// Which chart filename goes into which <img> element.
const CHART_MAP = {
    "rating_distribution.png": "chartRatingDistribution",
    "top_rated_movies.png": "chartTopRated",
    "popular_genres.png": "chartPopularGenres",
    "genre_average_rating.png": "chartGenreRating",
    "release_trend.png": "chartReleaseTrend",
    "rating_vs_popularity.png": "chartRatingVsPopularity",
    "rating_vs_votes.png": "chartRatingVsVotes",
};

const CHART_LABELS = {
    "rating_distribution.png": "Rating Distribution",
    "top_rated_movies.png": "Top Rated Movies",
    "popular_genres.png": "Popular Genres",
    "genre_average_rating.png": "Genre Rating Comparison",
    "release_trend.png": "Movie Release Trend",
    "rating_vs_popularity.png": "Popularity Analysis",
    "rating_vs_votes.png": "Vote Analysis",
};

const $ = (selector) => document.querySelector(selector);

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchJson(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
        let message = "Request failed (" + response.status + ")";
        try {
            const body = await response.json();
            if (body.error) message = body.error;
        } catch (_) {
            // ignore non-JSON error bodies
        }
        throw new Error(message);
    }
    return response.json();
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function renderKpis(stats) {
    $("#kpiTotal").textContent = stats.total_movies ?? "--";
    $("#kpiAvgRating").textContent = stats.average_rating ?? "--";
    $("#kpiMaxRating").textContent = stats.highest_rating ?? "--";
    $("#kpiGenre").textContent = stats.most_popular_genre ?? "--";
    $("#datasetBadge").textContent = stats.dataset_name ?? "--";
}

function renderInsights(analytics) {
    const list = $("#insightsList");
    list.innerHTML = "";
    const insights = analytics.insights || [];
    if (insights.length === 0) {
        $("#insightsSection").style.display = "none";
        return;
    }
    $("#insightsSection").style.display = "";
    insights.forEach((insight) => {
        const item = document.createElement("li");
        item.textContent = insight;
        list.appendChild(item);
    });
}

function renderCharts(analytics) {
    const available = new Set(analytics.charts || []);

    for (const [filename, elementId] of Object.entries(CHART_MAP)) {
        const img = document.getElementById(elementId);
        if (available.has(filename)) {
            img.src = "/output/charts/" + filename;
            img.style.display = "";
        } else {
            // The dataset does not support this chart: show a friendly note.
            img.style.display = "none";
            if (elementId === "chartRatingVsVotes") {
                $("#votesCard").style.display = "none";
            }
        }
    }
    if (available.has("rating_vs_votes.png")) {
        $("#votesCard").style.display = "";
    }
}

function renderTopRated(topRated) {
    const tbody = $("#topRatedTable");
    tbody.innerHTML = "";
    topRated.forEach((movie, index) => {
        const row = document.createElement("tr");
        const cells = [
            String(index + 1),
            movie.title || "n/a",
            movie.rating != null ? Number(movie.rating).toFixed(2) : "--",
            movie.votes != null ? Number(movie.votes).toLocaleString() : "--",
        ];
        cells.forEach((text) => {
            const td = document.createElement("td");
            td.textContent = text;
            row.appendChild(td);
        });
        tbody.appendChild(row);
    });
}

function renderGenreList(genres) {
    const list = $("#genreList");
    list.innerHTML = "";
    if (!genres || genres.length === 0) {
        list.innerHTML = '<li class="muted">No genre data available.</li>';
        return;
    }

    const maxCount = Math.max(...genres.map((g) => g.movie_count));

    // Keep the "All genres" option in sync with the genre list.
    const genreSelect = $("#genreFilter");
    const currentSelection = genreSelect.value;
    genreSelect.innerHTML = '<option value="">All genres</option>';
    genres.forEach((genre) => {
        const option = document.createElement("option");
        option.value = genre.genre;
        option.textContent = genre.genre;
        genreSelect.appendChild(option);
    });
    genreSelect.value = currentSelection;

    genres.forEach((genre) => {
        const li = document.createElement("li");

        const name = document.createElement("span");
        name.className = "genre-name";
        name.textContent = genre.genre;

        const bar = document.createElement("span");
        bar.className = "genre-bar";
        bar.style.width = Math.max(6, (genre.movie_count / maxCount) * 100) + "%";

        const count = document.createElement("span");
        count.className = "genre-count";
        const ratingText =
            genre.average_rating != null
                ? " | avg " + Number(genre.average_rating).toFixed(2)
                : "";
        count.textContent = genre.movie_count + " movies" + ratingText;

        li.appendChild(name);
        li.appendChild(bar);
        li.appendChild(count);
        list.appendChild(li);
    });
}

function renderSearchResults(data) {
    const section = $("#searchResultsSection");
    const tbody = $("#searchTable");
    tbody.innerHTML = "";
    $("#searchCount").textContent = "(" + data.count + " movies)";

    if (data.count === 0) {
        section.style.display = "";
        const row = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = 5;
        td.className = "muted";
        td.textContent = "No movies match the current filters.";
        row.appendChild(td);
        tbody.appendChild(row);
        return;
    }

    data.movies.forEach((movie) => {
        const row = document.createElement("tr");
        const cells = [
            movie.title || "n/a",
            movie.rating != null ? Number(movie.rating).toFixed(2) : "--",
            movie.genres || "--",
            movie.year != null ? movie.year : "--",
            movie.votes != null ? Number(movie.votes).toLocaleString() : "--",
        ];
        cells.forEach((text) => {
            const td = document.createElement("td");
            td.textContent = text;
            row.appendChild(td);
        });
        tbody.appendChild(row);
    });

    section.style.display = "";
}

function renderError(message) {
    $("#uploadStatus").className = "upload-status err";
    $("#uploadStatus").textContent = "Error: " + message;
}

// ---------------------------------------------------------------------------
// Data loading
// ---------------------------------------------------------------------------

async function loadDashboard() {
    try {
        const [stats, topRated, genres, analytics] = await Promise.all([
            fetchJson("/api/stats"),
            fetchJson("/api/top-rated"),
            fetchJson("/api/genres"),
            fetchJson("/api/analytics"),
        ]);

        renderKpis(stats);
        renderTopRated(topRated.top_rated || []);
        renderGenreList(genres.genres || []);
        renderInsights(analytics);
        renderCharts(analytics);
    } catch (error) {
        renderError(error.message);
    }
}

function applySearch() {
    const params = new URLSearchParams();
    const query = $("#searchInput").value.trim();
    const genre = $("#genreFilter").value;
    const minRating = $("#minRating").value;
    const maxRating = $("#maxRating").value;

    if (query) params.set("q", query);
    if (genre) params.set("genre", genre);
    if (minRating) params.set("min_rating", minRating);
    if (maxRating) params.set("max_rating", maxRating);

    fetchJson("/api/movies?" + params.toString())
        .then(renderSearchResults)
        .catch(renderError);
}

// ---------------------------------------------------------------------------
// Events
// ---------------------------------------------------------------------------

function attachEvents() {
    $("#applyFilters").addEventListener("click", applySearch);
    $("#searchInput").addEventListener("keydown", (event) => {
        if (event.key === "Enter") applySearch();
    });

    $("#uploadForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const fileInput = $("#fileInput");
        const status = $("#uploadStatus");

        if (!fileInput.files.length) {
            status.className = "upload-status err";
            status.textContent = "Please choose a CSV file first.";
            return;
        }

        status.className = "upload-status";
        status.textContent = "Uploading and analyzing...";

        const formData = new FormData();
        formData.append("file", fileInput.files[0]);

        try {
            const result = await fetchJson("/api/upload", {
                method: "POST",
                body: formData,
            });
            status.className = "upload-status ok";
            status.textContent = result.message;
            $("#fileInput").value = "";
            await loadDashboard();
        } catch (error) {
            status.className = "upload-status err";
            status.textContent = "Upload failed: " + error.message;
        }
    });

    $("#resetBtn").addEventListener("click", async () => {
        const status = $("#uploadStatus");
        status.className = "upload-status";
        status.textContent = "Loading sample dataset...";
        try {
            await fetchJson("/api/reset", { method: "POST" });
            status.className = "upload-status ok";
            status.textContent = "Sample dataset loaded.";
            await loadDashboard();
        } catch (error) {
            status.className = "upload-status err";
            status.textContent = "Reset failed: " + error.message;
        }
    });
}

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
    attachEvents();
    loadDashboard();
});
