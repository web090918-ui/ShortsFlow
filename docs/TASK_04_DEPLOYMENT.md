# Task 04 Cloud Run Deployment

## Scope

Task 04 adds durable processing-job state, Cloud Tasks dispatch, and an authenticated Worker endpoint. It does not run transcript, AI candidate generation, ranking, or rendering. The Worker completes a bootstrap step and records `next_step=TRANSCRIPT`; Task 05 replaces that bootstrap operation.

The same FastAPI application serves the public API and the Worker route. This remains one backend codebase and one Cloud Run service, not a microservice split.

## Runtime topology

```text
Vercel Next.js
-> Cloud Run FastAPI
   -> Firestore processing_jobs
   -> Cloud Tasks queue
      -> POST /worker/process with Google OIDC
```

The Cloud Run service may accept unauthenticated traffic for the public API during MVP testing. `/worker/process` separately validates the Google-signed OIDC token, its audience, and the configured service-account email. Do not set `SHORTSFLOW_WORKER_AUTH_MODE=google_oidc` until the Worker URL and service account are configured.

## Resources

Use `asia-northeast3` for all regional resources:

- Cloud Run service: `shortflow`
- Firestore Native database: `shortflow`
- Cloud Tasks queue: `shortsflow-processing`
- Runtime/task identity: `shortsflow-runtime@PROJECT_ID.iam.gserviceaccount.com`

Cloud Run, Cloud Tasks, and Firestore all support the Seoul region.

## First Cloud Run deployment

In Cloud Run, create a service from the GitHub repository:

- Repository: `web090918-ui/ShortsFlow`
- Branch: `main`
- Continuous deployment: Cloud Build
- Build type: Dockerfile
- Dockerfile source location: `/Dockerfile`
- Service name: `shortflow`
- Region: `asia-northeast3`
- Authentication: allow unauthenticated invocations for the current public MVP API
- Container port: `8080`
- Minimum instances: `0`
- Maximum instances: `2` for initial validation
- Request timeout: `900` seconds
- Container concurrency: `1` for media-processing safety

The first deployment can use the default in-memory/local settings. Its purpose is to obtain the stable Cloud Run service URL and verify `GET /health`.

## Required Google Cloud resources

Enable these APIs:

- Cloud Run Admin API
- Cloud Build API
- Artifact Registry API
- Cloud Tasks API
- Firestore API

Create Firestore in Native mode in `asia-northeast3`. Its location cannot be changed after creation. If the database ID is not `(default)`, set `SHORTSFLOW_FIRESTORE_DATABASE` to the exact ID.

Create the `shortsflow-processing` Cloud Tasks queue in `asia-northeast3` with a maximum of three attempts for initial validation.

Create the `shortsflow-runtime` service account. The Cloud Run service runs as this identity. Grant it only the permissions needed to read/write Firestore and enqueue Cloud Tasks. It must also be permitted to act as the OIDC service account used by the task. Do not download a long-lived service-account key; Cloud Run uses Application Default Credentials.

## Cloud Run environment

After the first deployment returns its `run.app` URL, configure a new revision with:

```text
SHORTSFLOW_APP_ENV=production
SHORTSFLOW_FRONTEND_ORIGIN=https://shortsflow-weld.vercel.app
SHORTSFLOW_TUNELIO_API_KEY=<Vercel과 동일한 서버 전용 키>
SHORTSFLOW_JOB_REPOSITORY_BACKEND=firestore
SHORTSFLOW_TASK_DISPATCHER_BACKEND=cloud_tasks
SHORTSFLOW_WORKER_AUTH_MODE=google_oidc
SHORTSFLOW_GCP_PROJECT_ID=<project-id>
SHORTSFLOW_GCP_LOCATION=asia-northeast3
SHORTSFLOW_FIRESTORE_DATABASE=shortflow
SHORTSFLOW_CLOUD_TASKS_QUEUE=shortsflow-processing
SHORTSFLOW_WORKER_URL=https://<cloud-run-service>.run.app
SHORTSFLOW_WORKER_OIDC_AUDIENCE=https://<cloud-run-service>.run.app
SHORTSFLOW_WORKER_SERVICE_ACCOUNT_EMAIL=shortsflow-runtime@<project-id>.iam.gserviceaccount.com
SHORTSFLOW_PROCESSING_MAX_ATTEMPTS=3
```

Store `SHORTSFLOW_TUNELIO_API_KEY` as a Cloud Run secret rather than committing it. The Worker URL and OIDC audience use the service origin without `/worker/process`; the dispatcher appends the route.

## Validation

1. `GET /health` returns `200`.
2. `POST /processing-jobs` returns `202` and `QUEUED`.
3. A Firestore `processing_jobs` document is created.
4. Cloud Tasks invokes `/worker/process` with OIDC.
5. `GET /processing-jobs/{id}` reaches `COMPLETED`, progress `100`, and `result.next_step=TRANSCRIPT`.
6. Replaying the same Worker payload leaves `attempt_count` unchanged after completion.
7. A request to `/worker/process` without the OIDC token is rejected.

Do not start Task 05 until this deployment path passes the validation above.

## Validation result

Task 04 passed deployment validation on 2026-09-27 using:

- Cloud Run: `https://shortflow-268642207702.asia-northeast3.run.app`
- Firestore database: `shortflow`
- Cloud Tasks queue: `shortsflow-processing`
- Runtime and task identity: `shortsflow-runtime@aza-ceo.iam.gserviceaccount.com`

The test job moved from `QUEUED` to `COMPLETED`, reported progress `100`, ran
once, and recorded `result.next_step=TRANSCRIPT`. Calling `/worker/process`
without an OIDC bearer token returned `401`. Duplicate terminal delivery is
covered by the backend test suite. Task 04 is complete; transcript processing
remains explicitly deferred to Task 05.
