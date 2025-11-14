# Changelog

All notable changes to the Active-Active Cost Analysis project.

---

## [2.1.2] - 2025-11-14

### Fixed
- **Duplicate Chart Removed**: Removed full-width "Cluster Age vs Savings Potential" chart (duplicate of "Age vs Savings Correlation")
- **URL Path Prefix**: Fixed Runs History table onclick handler to use `buildUrl()` for proper `/aac` prefix support in Load Balancer routing

### Changed
- **Charts Page**: Kept only "Age vs Savings Correlation" chart, removed redundant full-width version
- **JavaScript**: Updated onclick handler from direct URL to `buildUrl('top-savings?run_id=...')` for consistent path prefix handling

---

## [2.1.1] - 2025-11-14

### Fixed
- **Module Import Error**: Moved `aa_database.py` and `aa_report_automation.py` from `rcp/` to root directory
- **Docker Build**: Simplified `.dockerignore` to exclude only `aa_report_automation.py` and `rcp/` folder
- **Import Statement**: Changed from `from rcp.aa_database import AADatabase` to `from aa_database import AADatabase`

---

## [2.1.0] - 2025-11-14

### Added
- **Software Version Column**: Replaced "Redis Version" with "Software Version" across all tables and charts
- **Cluster Age Column**: Added cluster age calculation based on creation date
  - Displays in years (1 decimal) if >= 365 days
  - Displays in days if < 365 days
  - Color-coded badges (yellow for old, blue for new)
- **Database Schema Updates**:
  - Added `software_version` field to `cluster_metadata` table
  - Added `creation_date` field to `cluster_metadata` table
  - Maintained backward compatibility with `redis_version` and `created_at` fields
- **Dashboard Metrics Updates**:
  - Added "Total AA Spend" card (replaces "Top Cloud Provider")
  - Added "Optimization Rate" card (replaces "Avg Savings per Cluster")
  - Added "Avg Cluster Age" card (replaces "Most Used Instance Type")
  - Moved "Top Cloud Provider" to operational metrics section

### Changed
- **API Endpoints**: Updated all chart endpoints to use `softwareVersion` parameter instead of `redisVersion`
  - `/api/filters/software-versions` (renamed from `/api/filters/redis-versions`)
  - `/api/charts/software-version-analysis` (renamed from `/api/charts/redis-version-analysis`)
  - All other chart endpoints updated to accept `softwareVersion` parameter
- **Frontend Filters**: Updated all filter dropdowns and JavaScript to use "Software Version"
- **Database Queries**: All queries now use `COALESCE(cm.software_version, cm.redis_version)` for backward compatibility
- **Docker Configuration**: Updated `.dockerignore` to include `rcp/aa_database.py` while excluding automation scripts

### Fixed
- Docker build now correctly includes `rcp/aa_database.py` module
- Date parsing handles ISO format with timezone indicators

### Documentation
- Updated `README.md` with new project structure
- Updated `ENVIRONMENT_VARIABLES.md` with database requirements
- Updated `DEPLOYMENT.md` with schema requirements and Docker notes
- Added comprehensive documentation suite (QUICKSTART.md, SERVER_SETUP.md, WRAPPER_README.md, DOCS_INDEX.md)

### Technical Details
- **Backward Compatibility**: Uses SQL `COALESCE()` to fallback from new fields to legacy fields
- **Date Handling**: Parses ISO 8601 dates with `.replace('Z', '+00:00')` for timezone support
- **Badge Styling**: 
  - Cluster age >= 1 year: `badge bg-warning` (yellow)
  - Cluster age < 1 year: `badge bg-info` (blue)

---

## [2.0.0] - Previous Version

### Features
- Flask web dashboard for cluster optimization visualization
- SQLite database with historical tracking
- Interactive charts with Chart.js
- Cloud Run deployment with GCS volume mount
- Path-based routing support for Load Balancer
- Responsive Bootstrap 5 UI

---

## Migration Guide

### From v2.1.1 to v2.1.2

**No Code Changes Required:**
- Charts automatically updated
- URL routing automatically fixed
- No database changes needed

### From v2.0.0 to v2.1.0

**Database Migration:**

If you have an existing database, you need to add the new columns:

```sql
-- Add new columns to cluster_metadata table
ALTER TABLE cluster_metadata ADD COLUMN software_version TEXT;
ALTER TABLE cluster_metadata ADD COLUMN creation_date TEXT;

-- Create index for software_version
CREATE INDEX IF NOT EXISTS idx_cluster_metadata_software_version 
ON cluster_metadata(software_version);

-- Optional: Copy data from old columns to new columns
UPDATE cluster_metadata SET software_version = redis_version WHERE software_version IS NULL;
UPDATE cluster_metadata SET creation_date = created_at WHERE creation_date IS NULL;
```

**No Code Changes Required:**
- The application automatically handles both old and new database schemas
- Uses `COALESCE()` to fallback to legacy fields if new fields are NULL

**Cloud Run Deployment:**
1. Update `.dockerignore` (already done in repository)
2. Rebuild and redeploy Docker image
3. Upload updated database to GCS bucket
4. No environment variable changes needed

---

## Support

For questions or issues, contact: dobri.boyadzhiev@redis.com

