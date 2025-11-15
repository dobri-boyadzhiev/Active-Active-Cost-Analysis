# Google Cloud Run Deployment

Complete guide for deploying Active-Active Cost Analysis to Google Cloud Run.

---

## Prerequisites

1. **Google Cloud Project** with billing enabled
2. **gcloud CLI** installed and authenticated
3. **GitHub Repository** with application code
4. **GCS Bucket** for database storage (create manually)
5. **Database file** with required schema (see Database Schema Requirements below)

---

## Setup Steps

### 1. Create GCS Bucket

```bash
# Create bucket for database storage
gsutil mb -l europe-west1 gs://YOUR_BUCKET_NAME

# Upload database file
gsutil cp aa_report_cache.db gs://YOUR_BUCKET_NAME/
```

### 2. Generate SECRET_KEY

```bash
python -c "import os; print(os.urandom(24).hex())"
```

Save the output - you'll need it for deployment.

### 3. Deploy to Cloud Run

#### Option A: Deploy from GitHub (Recommended)

1. Go to [Cloud Run Console](https://console.cloud.google.com/run)
2. Click **Create Service**
3. Select **Continuously deploy from a repository**
4. Connect your GitHub repository
5. Configure:
   - **Region**: `europe-west1`
   - **Authentication**: Allow unauthenticated invocations
   - **Container port**: `8080`
   - **Memory**: `512 MiB`
   - **CPU**: `1`
   - **Min instances**: `0`
   - **Max instances**: `10`
   - **Timeout**: `300s`

6. **Environment Variables**:
   ```
   SECRET_KEY=<your-generated-key>
   FLASK_DEBUG=False
   GCS_MOUNT_PATH=/mnt/gcs
   PATH_PREFIX=/aac
   ```

7. **Volumes**:
   - Click **Add Volume**
   - Type: **Cloud Storage bucket**
   - Name: `gcs-volume`
   - Bucket: `YOUR_BUCKET_NAME`
   - Mount path: `/mnt/gcs`
   - Read-only: Yes (recommended)

8. Click **Create**

#### Option B: Deploy with gcloud CLI

```bash
gcloud run deploy aa-cost-analysis \
  --source . \
  --region europe-west1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars SECRET_KEY=<your-generated-key> \
  --set-env-vars FLASK_DEBUG=False \
  --set-env-vars GCS_MOUNT_PATH=/mnt/gcs \
  --set-env-vars PATH_PREFIX=/aac \
  --memory 512Mi \
  --cpu 1 \
  --timeout 300 \
  --max-instances 10 \
  --min-instances 0 \
  --add-volume name=gcs-volume,type=cloud-storage,bucket=YOUR_BUCKET_NAME \
  --add-volume-mount volume=gcs-volume,mount-path=/mnt/gcs
```

**Replace `YOUR_BUCKET_NAME` with your actual GCS bucket name.**

---

## Load Balancer Setup

To serve the application at `https://cloudops.redis.com/aac/`:

### 1. Create Backend Service

```bash
gcloud compute backend-services create aa-cost-analysis-backend \
  --global \
  --load-balancing-scheme=EXTERNAL_MANAGED \
  --protocol=HTTPS
```

### 2. Add Cloud Run NEG

```bash
# Create serverless NEG
gcloud compute network-endpoint-groups create aa-cost-analysis-neg \
  --region=europe-west1 \
  --network-endpoint-type=serverless \
  --cloud-run-service=aa-cost-analysis

# Add to backend service
gcloud compute backend-services add-backend aa-cost-analysis-backend \
  --global \
  --network-endpoint-group=aa-cost-analysis-neg \
  --network-endpoint-group-region=europe-west1
```

### 3. Configure URL Map

```bash
# Create path matcher for /aac/*
gcloud compute url-maps add-path-matcher YOUR_URL_MAP \
  --path-matcher-name=aa-cost-analysis-matcher \
  --default-service=YOUR_DEFAULT_BACKEND \
  --backend-service-path-rules="/aac/*=aa-cost-analysis-backend"
```

**Replace `YOUR_URL_MAP` and `YOUR_DEFAULT_BACKEND` with your existing Load Balancer resources.**

---

## Database Schema Requirements

The database must have the following schema in `cluster_metadata` table:

```sql
CREATE TABLE cluster_metadata (
    mc_uid TEXT PRIMARY KEY,
    cluster_name TEXT,
    cloud_provider TEXT,
    region TEXT,
    software_version TEXT,      -- Required: Software version
    creation_date TEXT,          -- Required: Cluster creation date (ISO format)
    redis_version TEXT,          -- Optional: Legacy field (fallback)
    created_at TEXT              -- Optional: Legacy field (fallback)
);
```

**Important:** The application uses `COALESCE(software_version, redis_version)` for backward compatibility.

---

## Updating the Database

To update the database with new data:

```bash
# Upload new database file
gsutil cp aa_report_cache.db gs://YOUR_BUCKET_NAME/

# Cloud Run will automatically use the updated file
# No redeployment needed!
```

---

## Monitoring

### View Logs

```bash
gcloud run services logs read aa-cost-analysis --region europe-west1
```

### View Metrics

Go to [Cloud Run Console](https://console.cloud.google.com/run) → Select service → **Metrics** tab

---

## Troubleshooting

### Database not found

**Error**: `FileNotFoundError: aa_report_cache.db`

**Solution**: 
1. Verify bucket name in volume configuration
2. Check database file exists in bucket: `gsutil ls gs://YOUR_BUCKET_NAME/`
3. Verify `GCS_MOUNT_PATH` environment variable is set to `/mnt/gcs`

### 404 errors on all routes

**Error**: All pages return 404

**Solution**:
1. Verify `PATH_PREFIX` is set to `/aac`
2. Check Load Balancer path rules include `/aac/*`
3. Verify `APPLICATION_ROOT` is configured in Flask app

### Permission denied on GCS bucket

**Error**: `Permission denied` when accessing database

**Solution**:
1. Grant Cloud Run service account access to bucket:
   ```bash
   gsutil iam ch serviceAccount:SERVICE_ACCOUNT_EMAIL:objectViewer gs://YOUR_BUCKET_NAME
   ```
2. Find service account email in Cloud Run service details

### Missing database columns

**Error**: `no such column: software_version` or `no such column: creation_date`

**Solution**:
1. Verify database schema includes `software_version` and `creation_date` columns
2. Update database schema or regenerate database with new schema
3. See "Database Schema Requirements" section above

---

## Security

- **HTTPS**: Automatically provided by Cloud Run
- **Read-only database**: GCS volume mounted read-only
- **No public write access**: Application only reads data
- **Authentication**: Currently allows unauthenticated access
  - Add Cloud IAP or custom auth if needed

---

## Cost Optimization

- **Min instances = 0**: No cost when idle
- **512 MiB memory**: Sufficient for read-only SQLite operations
- **1 CPU**: Adequate for Flask application
- **GCS storage**: ~$0.02/GB/month (Standard storage)

**Estimated monthly cost**: $5-15 (depending on traffic)

---

## Rollback

To rollback to previous revision:

```bash
# List revisions
gcloud run revisions list --service aa-cost-analysis --region europe-west1

# Rollback to specific revision
gcloud run services update-traffic aa-cost-analysis \
  --region europe-west1 \
  --to-revisions REVISION_NAME=100
```

---

## Docker Build Notes

The `.dockerignore` file is configured to:
- **Include** `aa_database.py` (required by the application)
- **Exclude** `aa_report_automation.py` (automation script, not needed in Cloud Run)
- **Exclude** `rcp/` folder (legacy location)
- **Exclude** `*.db` files (database is mounted from GCS)
- **Exclude** documentation files from root

This ensures the Docker image contains only necessary files for the web application.

---

## Additional Resources

- [Cloud Run Documentation](https://cloud.google.com/run/docs)
- [GCS Volumes for Cloud Run](https://cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [Environment Variables Reference](ENVIRONMENT_VARIABLES.md)

