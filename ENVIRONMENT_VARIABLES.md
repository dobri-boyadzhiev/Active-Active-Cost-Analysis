# Environment Variables Reference

Complete reference for all environment variables used in Active-Active Cost Analysis.

---

## Required Variables

### `SECRET_KEY`

**Purpose**: Flask session encryption and security

**Generate**:
```bash
python -c "import os; print(os.urandom(24).hex())"
```

**Example**: `f86e2e839582e12cfa91a5a00c5620fe1affda5390c5b2be`

**Security**:
- Keep secret - never commit to Git
- Use different keys for dev/staging/prod
- Rotate periodically

**Cloud Run**:
```bash
--set-env-vars SECRET_KEY=<your-generated-key>
```

---

### `GCS_MOUNT_PATH`

**Purpose**: Path where GCS bucket is mounted for database persistence

**Default**: `/mnt/gcs`

**Cloud Run**:
```bash
--set-env-vars GCS_MOUNT_PATH=/mnt/gcs
--add-volume name=gcs-volume,type=cloud-storage,bucket=YOUR_BUCKET_NAME
--add-volume-mount volume=gcs-volume,mount-path=/mnt/gcs
```

**Note**: Database file (`aa_report_cache.db`) must exist in the GCS bucket

---

### `PATH_PREFIX`

**Purpose**: URL path prefix for routing through Google Load Balancer

**Default**: `` (empty, no prefix)

**Example**: `/aac` (for `https://cloudops.redis.com/aac/`)

**Cloud Run**:
```bash
--set-env-vars PATH_PREFIX=/aac
```

**Note**: 
- Application will be accessible at `https://your-domain.com/aac/`
- Load Balancer must be configured with matching path rules

---

## Optional Variables

### `FLASK_DEBUG`

**Purpose**: Enable/disable Flask debug mode

**Default**: `False`

**Values**: `True`, `False`, `1`, `0`, `yes`, `no`

**Development**:
```bash
FLASK_DEBUG=True
```

**Production**:
```bash
FLASK_DEBUG=False
```

**Security**: **NEVER** enable debug mode in production!

---

### `FLASK_HOST`

**Purpose**: Host address for Flask server

**Default**: `127.0.0.1` (localhost only)

**Values**: 
- `127.0.0.1` - localhost only
- `0.0.0.0` - all network interfaces

**Local Development**:
```bash
FLASK_HOST=127.0.0.1
```

**Cloud Run**: Not needed (managed by Cloud Run)

---

### `FLASK_PORT`

**Purpose**: Port for Flask server

**Default**: `5000`

**Local Development**:
```bash
FLASK_PORT=5000
```

**Cloud Run**: Not needed (uses `PORT` environment variable automatically set to `8080`)

---

### `PORT`

**Purpose**: Port for production server (Gunicorn)

**Default**: `8080`

**Cloud Run**: Automatically set by Cloud Run - **DO NOT override**

---

## Configuration Examples

### Local Development (.env file)

```bash
SECRET_KEY=f86e2e839582e12cfa91a5a00c5620fe1affda5390c5b2be
FLASK_DEBUG=True
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
```

### Cloud Run Production

**Required**:
```bash
SECRET_KEY=<your-generated-key>
GCS_MOUNT_PATH=/mnt/gcs
PATH_PREFIX=/aac
```

**Recommended**:
```bash
SECRET_KEY=<your-generated-key>
FLASK_DEBUG=False
GCS_MOUNT_PATH=/mnt/gcs
PATH_PREFIX=/aac
```

---

## Setting Environment Variables

### Local Development

Create `.env` file in project root:

```bash
SECRET_KEY=your-secret-key-here
FLASK_DEBUG=True
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
```

### Cloud Run (Console)

1. Go to Cloud Run service
2. Click **Edit & Deploy New Revision**
3. Go to **Variables & Secrets** tab
4. Add environment variables

### Cloud Run (gcloud CLI)

```bash
gcloud run services update aa-cost-analysis \
  --region europe-west1 \
  --set-env-vars SECRET_KEY=<key>,FLASK_DEBUG=False,GCS_MOUNT_PATH=/mnt/gcs,PATH_PREFIX=/aac
```

---

## Database Schema Requirements

The application expects the following fields in `cluster_metadata` table:

- `software_version` (TEXT) - Software version (preferred)
- `creation_date` (TEXT) - Cluster creation date in ISO format
- `redis_version` (TEXT) - Legacy field, used as fallback if `software_version` is NULL
- `created_at` (TEXT) - Legacy field, used as fallback if `creation_date` is NULL

**Backward Compatibility:** The application uses `COALESCE(software_version, redis_version)` to support both old and new data.

---

## Validation

The application logs configuration on startup:

```
🔵 GCS Mount Path: /mnt/gcs
🔵 Database Path: /mnt/gcs/aa_report_cache.db
🔵 Path Prefix: /aac
```

Check Cloud Run logs to verify:

```bash
gcloud run services logs read aa-cost-analysis --region europe-west1 --limit 50
```

---

## Troubleshooting

### Missing SECRET_KEY

**Error**: `RuntimeError: The session is unavailable because no secret key was set.`

**Solution**: Set `SECRET_KEY` environment variable

### Wrong PATH_PREFIX

**Symptom**: 404 errors on all routes

**Solution**: 
1. Verify `PATH_PREFIX=/aac` is set
2. Check Load Balancer path rules match

### Database not found

**Error**: `FileNotFoundError: /mnt/gcs/aa_report_cache.db`

**Solution**:
1. Verify `GCS_MOUNT_PATH=/mnt/gcs` is set
2. Check database exists in GCS bucket
3. Verify volume mount configuration

---

## Security Best Practices

1. **Never commit `.env` file** - add to `.gitignore`
2. **Use Secret Manager** for production secrets (optional)
3. **Rotate SECRET_KEY** periodically
4. **Disable debug mode** in production (`FLASK_DEBUG=False`)
5. **Use HTTPS** (automatic with Cloud Run)
6. **Limit environment variable access** to authorized users only

---

## Additional Resources

- [Flask Configuration](https://flask.palletsprojects.com/en/3.0.x/config/)
- [Cloud Run Environment Variables](https://cloud.google.com/run/docs/configuring/environment-variables)
- [Secret Manager](https://cloud.google.com/secret-manager/docs)

