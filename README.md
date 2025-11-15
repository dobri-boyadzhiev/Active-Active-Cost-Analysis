# Active-Active Cost Analysis

Flask web dashboard for visualizing Redis cluster optimization data and cost savings opportunities.

## Documentation

**[DOCS_INDEX.md](DOCS_INDEX.md)** - Complete documentation index

### Quick Links
- **[QUICKSTART.md](QUICKSTART.md)** - Quick reference for production server
- **[SERVER_SETUP.md](SERVER_SETUP.md)** - Complete production setup documentation
- **[WRAPPER_README.md](WRAPPER_README.md)** - Why wrapper scripts?
- **[SETUP.md](SETUP.md)** - General setup instructions
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and changes
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Cloud Run deployment guide
- **[ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md)** - Environment variables reference
- **[RCP.md](RCP.md)** - RCP automation tool documentation

---

## Quick Start

### Local Development

**Prerequisites**: Python 3.12+, database file `aa_report_cache.db` in project root

**Option 1: Quick Start Script (Recommended)**

```bash
# Windows
.\run.ps1

# Linux/Mac
chmod +x run.sh
./run.sh
```

**Option 2: Manual Start**

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

**That's it!** No environment variables needed for local testing.

### Cloud Run Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md)

---

## Features

| Page | Purpose |
|------|---------|
| **Dashboard** (`/`) | Financial metrics, top savings, trends |
| **Charts** (`/charts`) | Interactive analytics with filters |
| **Savings** (`/top-savings`) | Ranked optimization opportunities |
| **Cluster Details** (`/cluster/<id>`) | Current vs optimal comparison |

---

## Tech Stack

- **Backend**: Flask 3.0, Python 3.12
- **Database**: SQLite (read-only, mounted from GCS bucket)
- **Frontend**: Bootstrap 5, Chart.js, DataTables
- **Deployment**: Google Cloud Run with GCS volume mount

---

## Project Structure

```
├── app.py                    # Flask application
├── aa_database.py            # Database layer
├── aa_report_automation.py   # Automation script (excluded from Docker)
├── requirements.txt          # Dependencies
├── Dockerfile                # Cloud Run container
├── .dockerignore             # Docker build exclusions
├── static/
│   ├── css/style.css
│   └── js/main.js
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── charts.html
    ├── top_savings.html
    └── cluster_details.html
```

---

## Configuration

### Environment Variables

See [ENVIRONMENT_VARIABLES.md](ENVIRONMENT_VARIABLES.md) for complete reference.

**Required for Cloud Run:**
- `SECRET_KEY` - Flask session encryption
- `GCS_MOUNT_PATH` - Path to mounted GCS bucket (default: `/mnt/gcs`)
- `PATH_PREFIX` - URL prefix for Load Balancer routing (e.g., `/aac`)

---

## Database

SQLite database (`aa_report_cache.db`) stored in GCS bucket with schema:

- **runs** - Optimization run metadata
- **cluster_results** - Per-cluster optimization results
- **cluster_singles** - Current vs optimal configurations
- **cluster_metadata** - Cloud provider, region, software version, creation date

---

## License

Internal tool for Redis cost analysis.

