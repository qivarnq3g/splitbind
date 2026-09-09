# Local and offline operation

This runbook describes the P2 Compose boundaries. P2 provides static topology and parser validation only. P3 supplies matching container builds and hardening, B1/B6 supply application health behavior, and P7 supplies the release image inventory and offline-demo script. Do not treat a successful `docker compose config` render as runtime health evidence.

## Demo trình bày trong năm phút

Demo trình bày nhanh này khác với offline release drill do P7 sở hữu. Nó chạy Django API, đúng một `run_demo_worker` và Vite trực tiếp từ toolchain đã chuẩn bị trong repository; Compose project riêng `splitbind-demo` chỉ chạy `minio-demo` tại `127.0.0.1:9000`. SQLite, dữ liệu MinIO, secret tổng hợp, PID state và log nằm trong `artifacts/demo/`, vốn bị Git bỏ qua. Đây là runtime trình bày cục bộ, không phải bằng chứng concurrency của PostgreSQL, RabbitMQ, Rust worker hay production.

Trước khi chạy, chuẩn bị Python 3.11 `.venv` với extra `demo,test`, dependency workspace Node 24/npm 12, Docker Compose phù hợp, Docker daemon đang chạy và image chính xác `minio/minio:RELEASE.2025-09-07T16-13-09Z` đã nạp cục bộ. Runner kiểm tra toàn bộ điều kiện trước khi tạo state; nó không cài package, pull/build image, triển khai tài nguyên hay liên hệ Azure, R2, Key Vault hoặc DNS công khai.

Từ thư mục gốc repository, chạy:

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/run_demo.ps1
```

Chỉ sau khi cả ba PID API/worker/Vite còn đúng executable và start time, Compose xác nhận đúng service `minio-demo`, rồi MinIO, API và Vite trả đúng status/payload mong đợi, runner mới in URL `http://127.0.0.1:5173`, username `demo-admin`, mật khẩu tổng hợp, vị trí log và lệnh dừng. Nếu thiếu Python dependency, cài từ nguồn package đã được cho phép bằng lệnh runner nêu; nếu Docker daemon chưa chạy, khởi động Docker Desktop ở chế độ Linux containers; nếu thiếu image, dùng `docker load` với archive cục bộ đã phê duyệt. Không đổi runner để tự tải dependency hoặc image.

Luồng trình bày khoảng năm phút:

1. Mở URL runner in ra và đăng nhập bằng credential tổng hợp vừa được in.
2. Mở **Cấp phát**, dùng UUID người nhận tổng hợp do runner/seed cung cấp, chọn một PDF tổng hợp nhỏ không chứa dữ liệu thật, rồi gửi yêu cầu.
3. Theo dõi bốn giai đoạn job đến khi thành công và tải PDF đã đánh dấu bằng nút trên trang kết quả.
4. Mở **Xác minh**, tải chính PDF vừa nhận, chờ job hoàn tất và mở kết quả kiểm chứng.
5. Giải thích riêng các fact về exact hash, fingerprint, manifest và giới hạn. Nhãn thuật toán luôn là `experimental_unreleased_fingerprint_v2`; không có fingerprint profile được promote và demo không tạo bằng chứng manifest ký. Kết quả không chứng minh ai đã làm rò rỉ, chỉnh sửa hoặc phân phối tài liệu.

Dừng đúng instance demo bằng:

```powershell
powershell -ExecutionPolicy Bypass -File infra/scripts/run_demo.ps1 -Stop
```

Lệnh dừng revalidate executable identity và start time trước khi dừng từng PID, thử dừng hết các PID độc lập, rồi luôn thử hạ đúng Compose project `splitbind-demo` mà không dùng `--volumes`. PID timeout hoặc mismatch không bị xóa khỏi state để người vận hành xử lý an toàn. SQLite, dữ liệu MinIO và secret tổng hợp được giữ lại để restart có thể lặp lại; xóa chúng chỉ khi đã xác minh đích chính xác và chấp nhận mất state demo. Nếu startup thất bại, runner rollback chỉ các process/service do lần gọi đó tạo và giữ log cùng PID chưa dừng được để chẩn đoán.

Ngày 2026-09-04, runner một lệnh đã được quan sát khởi động thành công MinIO, API, worker và Vite trên host Windows. Một E2E trình duyệt thật đã đăng nhập, cấp phát PDF tổng hợp, tải kết quả và tải lại chính kết quả đó để nhận trạng thái `VERIFIED_INTACT` mà không có lỗi console. Bằng chứng này chỉ xác nhận runtime demo cục bộ; nó không thay thế các gate PostgreSQL, RabbitMQ, Rust worker, R2 hoặc production.

## Local profiles

Run commands from the repository root. The local topology publishes only Caddy on `http://localhost:8080`; PostgreSQL, MinIO, RabbitMQ, the API, outbox publisher, and worker remain on the private Compose network.

| Profile | Services | Intended use |
| --- | --- | --- |
| `core` | Caddy, API, outbox, RabbitMQ, worker, PostgreSQL, MinIO | Normal application development |
| `research` | Python research image | Algorithm experiments without the application stack |
| `observability` | Prometheus | Local metric inspection only |
| `full` | All local services plus the end-to-end runner | Complete local verification after dependent tasks land |

Validate a profile without creating containers or contacting the Docker daemon:

```powershell
python infra/scripts/check_compose_capabilities.py
docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile core config --quiet
docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.local.yaml --profile full config --quiet
```

The preflight probes `docker compose config --help` for the exact `--format`, `--no-env-resolution`, and `--no-path-resolution` capabilities used by platform tests. It does not contact the Docker daemon and reports an upgrade action when an option is unavailable; the project does not guess a historical minimum Compose version.

After P3 has built the placeholder images and the application-specific environment is configured, operators may start the core profile with:

```powershell
docker compose -f infra/compose/compose.local.yaml --profile core up -d
```

Stop the same project with `docker compose -f infra/compose/compose.local.yaml --profile core down`. Preserve named data deliberately if later tasks add volumes; never add `--volumes` unless deletion of that exact local state is intended.

## Offline demonstration boundary

The offline topology contains only Caddy, API, outbox, RabbitMQ, worker, PostgreSQL, and MinIO. Its application network is internal, every service uses `pull_policy: never`, and every image variable requires a digest reference. It does not use Neon, Cloudflare R2, Azure Key Vault, public DNS, or a public hostname.

Static validation uses deterministic fake digests and clearly marked non-production values:

```powershell
docker compose --env-file infra/compose/config-test.env -f infra/compose/compose.offline.yaml config --quiet
```

Those config-test files are parser fixtures, not runnable credentials. Application startup must reject them when `ENVIRONMENT=production`.

P7 owns the executable offline procedure. Its `infra/scripts/offline-demo.ps1` will load an approved image archive, bind the exact digests recorded in `infra/release/offline-images.txt`, and generate disposable synthetic credentials and key files below ignored `artifacts/offline/keys/` before startup. Do not copy production secrets, private course documents, or real recipient data into the offline bundle. After the demonstration, stop the Compose project and remove only the script-created disposable key directory after verifying its resolved path and ownership.

## Production separation

Production is a separate topology with exactly Caddy, API, outbox, RabbitMQ, and worker. Neon PostgreSQL and Cloudflare R2 remain external. Host secret sources are under `/run/splitbind/secrets`; only the worker receives the manifest-signing, fingerprint, and integrity private files at `/run/secrets`. API and outbox receive their environment file but never those worker-private key mounts. Production publishes only ports 80 and 443 through Caddy.

The rendered production environment exposes only non-secret routing hints: `SPLITBIND_DATABASE_HOST` identifies the external Neon hostname for API and outbox, while `OBJECT_STORAGE_ENDPOINT` and `OBJECT_STORAGE_ENDPOINT_HINT` identify the same HTTPS Cloudflare R2 authority for API and worker. Object-store bucket and credentials use the exact `OBJECT_STORAGE_BUCKET`, `OBJECT_STORAGE_ACCESS_KEY`, and `OBJECT_STORAGE_SECRET_KEY` names in host-owned env files and never belong in the Compose file. B3 startup validation rejects endpoint user information, paths, queries, fragments, unsafe schemes, and production mismatch against the managed hint. Plain HTTP is accepted only when `ENVIRONMENT` explicitly names `local`, `offline`, or `test`; it is never a production fallback.

Validate a database host as a credential-free DNS authority before deployment:

```powershell
python infra/scripts/validate_database_host.py --database-host $env:NEON_DATABASE_HOST --required-suffix .neon.tech
```

The validator rejects user information, passwords, ports, schemes, paths, queries, fragments, whitespace, control characters, and names outside a lowercase ASCII DNS-host grammar. Static P2 tests use `.neon.tech.invalid`; a deployment preflight uses the real managed-service suffix `.neon.tech`. The validator never echoes a rejected host, so an accidentally supplied credential is not copied into diagnostics.

Validate the bounded P2 Caddy structure without downloading Caddy:

```powershell
python infra/scripts/validate_caddyfile.py
```

The validator accepts only this task's exact global block, site label, security headers, API/health reverse proxies, and static fallback, and emits structured JSON. It is deliberately not a general Caddy parser. P3 must additionally run the official `caddy validate` command inside the built web image; only that runtime-owned check proves compatibility with the packaged Caddy version.
