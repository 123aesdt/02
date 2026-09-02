# Full Runtime Verified Build Context Design

## Problem

The Full Runtime launcher currently passes the OneDrive-backed workspace directly to Docker Build. Docker Desktop can receive corrupted source bytes from that context: the host `backend/app/api/v1/task_events.py` is valid, while the built image contains NUL bytes and the backend exits during import.

## Approved design

- Stage only the required backend, frontend, and Qdrant build files beneath a uniquely named directory in the operating-system temporary directory, materializing every file through an explicit byte read/write instead of preserving OneDrive copy metadata.
- Compare SHA-256 hashes for every staged file with its source before invoking Docker.
- Disable BuildKit layer reuse so a previously corrupted cached `COPY` layer cannot enter a verified image.
- Build the backend image once and tag it for backend, migration, and both workers; build frontend and Qdrant from their verified staged contexts.
- Start Compose with `--no-build` so it cannot reopen the OneDrive workspace as a build context.
- Remove only a resolved temporary directory whose parent and name match the launcher-owned safe pattern.
- Keep the builder compatible with both Windows PowerShell 5.1, which the double-click batch launcher invokes, and PowerShell 7. Relative-path validation and SHA-256 calculation therefore use baseline .NET APIs instead of `Path.GetRelativePath` or `Get-FileHash`.
- Preserve `.docker.env`, volumes, application data, business behavior, and all existing service contracts.

## Verification

- Behavior tests run staging and hash validation without Docker under both `powershell.exe` 5.1 and `pwsh` 7.
- A launcher contract test requires the verified builder and forbids `compose up --build`.
- The recovered runtime must have a healthy backend and frontend, successful migration, running workers, matching host/image source hashes, and no pending Redis Stream deliveries.
