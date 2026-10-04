# Storage Gateway

A small FastAPI service that sits in front of an S3-compatible bucket (Cloudflare R2, MinIO, Backblaze B2, AWS S3, etc.). Clients upload and download files through simple HTTP endpoints and never need bucket credentials themselves.

## What the service does

- **Uploads** a file to your bucket under a unique key (`objects/<object_id>/<filename>`) and returns an `object_id`.
- **Tracks metadata** (filename, content type, created and expiry times) in a local SQLite database (`metadata.db`).
- **Serves downloads** by `object_id`, with the original filename and content type restored.
- **Deletes** objects on request, removing both the file in the bucket and its metadata record.
- **Expires files automatically.** Every object gets an expiry date of `TTL` days after upload. A background task runs once an hour and deletes expired objects from the bucket and the database.

```
Client ──HTTP──▶ Storage Gateway ──S3 API──▶ Bucket
                      │
                      └── SQLite (metadata.db)
```

## Project structure

```
app/
├── main.py                      # FastAPI app and /health
├── api/v1/routes.py             # /save, /load, /delete, /metadata
├── core/config.py               # Settings loaded from environment / .env
├── db/
│   ├── database.py              # SQLite engine and startup lifespan
│   └── models.py                # ObjectRecord table
└── services/
    ├── client.py                # boto3 S3 client
    ├── object_store.py          # save / load / delete / metadata logic
    └── cleanup_schedular.py     # hourly expired-object cleanup
tests/
└── client_test.py               # checks bucket connectivity
```

## Setup

### Requirements

- Python 3.11
- An S3-compatible bucket and an access key pair for it

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Then edit `.env`:

| Variable            | Required | Description                                                        |
| ------------------- | -------- | ------------------------------------------------------------------ |
| `CLOUD_ENDPOINT`    | Yes      | S3-compatible endpoint URL                                         |
| `ACCESS_TOKEN`      | Yes      | Access key ID                                                      |
| `API_KEY`           | Yes      | Secret access key                                                  |
| `SIGNATURE_VERSION` | Yes      | Signature version, typically `s3v4`                                |
| `TTL`               | Yes      | Days before an uploaded object expires and is deleted              |
| `BUCKET`            | Yes      | Name of the bucket to store objects in                             |
| `REGION`            | No       | Bucket region. Defaults to `auto` (use this for Cloudflare R2)     |
| `APP_NAME`          | No       | Display name. Defaults to `Storage Gateway`                        |



## Running

### Locally

From the project root:

```bash
uvicorn app.main:app --reload
```

The API is now available at `http://localhost:8000`. Interactive docs are at `http://localhost:8000/docs`.

On first start the service creates `metadata.db` in the directory you launched it from. Always launch it from the same directory, or the service will start with an empty metadata database.

### With Docker

```bash
docker build -t storage-gateway .
docker run -d -p 8000:8000 --env-file .env -v gateway_data:/data storage-gateway
```

The volume mounted at `/data` holds `metadata.db`. Without it, metadata is lost when the container is removed.

Run a **single worker only**. The cleanup scheduler runs inside the app process and metadata is stored in SQLite, so multiple workers would run the cleanup repeatedly and contend for the database.

### Tests

```bash
pip install pytest httpx
pytest
```

The existing test connects to your real bucket and expects the first bucket in the account to be named `s3-storage`. Update the assertion for your own bucket, and note that it needs valid credentials in `.env`.

## Endpoints

| Method   | Path        | Purpose                           | Input                                  |
| -------- | ----------- | --------------------------------- | -------------------------------------- |
| `GET`    | `/health`   | Liveness check                    | none                                   |
| `PUT`    | `/save`     | Upload a file                     | multipart form field `file`            |
| `GET`    | `/load`     | Download a file                   | query param `object_id`                |
| `GET`    | `/metadata` | Get a file's metadata             | query param `object_id`                |
| `DELETE` | `/delete`   | Delete a file and its metadata    | query param `object_id`                |

### `GET /health`

```json
{ "status": "ok" }
```

### `PUT /save`

Uploads a file and returns its record.

```bash
curl -X PUT http://localhost:8000/save -F "file=@report.pdf"
```

```json
{
  "object_id": "3f1c9c3e-7a52-4c0b-9d0e-2a5b8e4f1a77",
  "key": "objects/3f1c9c3e-7a52-4c0b-9d0e-2a5b8e4f1a77/report.pdf",
  "filename": "report.pdf",
  "content_type": "application/pdf",
  "created_at": "2026-10-04T06:30:00+00:00",
  "expires_at": "2026-10-11T06:30:00+00:00"
}
```

Keep the `object_id`. It is the handle for every other endpoint.

### `GET /load`

Streams the file back as an attachment with its original filename and content type.

```bash
curl -OJ "http://localhost:8000/load?object_id=<object_id>"
```

- `404` if the `object_id` is unknown
- `500` if the file could not be fetched from the bucket

### `GET /metadata`

Returns metadata without downloading the file.

```bash
curl "http://localhost:8000/metadata?object_id=<object_id>"
```

```json
{
  "object_id": "3f1c9c3e-7a52-4c0b-9d0e-2a5b8e4f1a77",
  "filename": "report.pdf",
  "content_type": "application/pdf",
  "created_at": "2026-10-04T06:30:00+00:00",
  "expires_at": "2026-10-11T06:30:00+00:00"
}
```

If no record exists for the `object_id`, the response is a message saying so.

### `DELETE /delete`

Removes the object from the bucket, then deletes its metadata record.

```bash
curl -X DELETE "http://localhost:8000/delete?object_id=<object_id>"
```

- `404` if the `object_id` is unknown
- `500` if deletion from the bucket failed (the metadata record is kept)

## Notes

- Objects are deleted automatically once their expiry time passes. The cleanup runs hourly, so deletion can lag expiry by up to an hour.
- The service has no authentication. Run it on a private network or put it behind a gateway or reverse proxy that handles access control.
- SQL statements are logged to the console (`echo=True` in `app/db/database.py`). Turn this off for production.