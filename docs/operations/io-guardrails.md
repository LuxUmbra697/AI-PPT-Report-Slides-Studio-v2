# Slide I/O guardrails — opt-in, maintenance approval required

These overlays are **proposals, not automatically enabled production settings**.
Checking them into Git or fetching them on a server does not change running containers.
Do not apply them until the owner approves the affected services and downtime window.

## Scope and evidence

An idle sample cannot identify the cause of a previous host stall or predict generation
and export peaks. Compare cgroup `io.stat`, process I/O deltas, log growth, memory pressure,
swap, and `sar` over the same time interval. Container Block I/O counters are cumulative,
not instantaneous throughput. Log-driver writes can be charged to host processes rather
than the application cgroup, so also inspect log-file growth without modifying those files.

Keep incident details, real volume IDs, private configurations and raw audit output outside
Git. Do not inspect unrelated customer documents or modify another application's data.

## Two independent changes

| Overlay | Services affected | Expected impact when approved and applied |
| --- | --- | --- |
| `deploy/compose.slide-io.yml` | API, worker, PostgreSQL, Redis | Service-by-service recreation; Slide requests/jobs may be interrupted |
| `deploy/compose.gateway-logs.yml` | Nginx only | Gateway recreation can briefly disconnect **every** site behind it; separate approval required |

Both use `json-file`, `max-size: 3m`, `max-file: 2`, non-blocking delivery and a 256k
per-container buffer. These bound retained container logs, not database, media or host logs.
Under sustained pressure a full non-blocking buffer **drops messages, including errors**;
it trades completeness for preventing application stalls. Uvicorn still emits warnings and
errors; only normal access messages and informational startup output are suppressed in the
application overlay. ARQ warning/error behavior is unchanged.

`unless-stopped` restores a container after a host reboot unless deliberately stopped.
No overlay changes PostgreSQL durability, Redis snapshot policy, queue contents, worker
concurrency, CPU, memory or block-I/O quotas. Hard caps need representative load measurements;
an arbitrarily small limit can introduce OOM failures or timeouts. Never throttle a shared
gateway based on one application's idle statistics.

## Preflight (read-only)

1. Resolve the actual Compose project, working directory, environment-file argument,
   all override files, networks, gateway mounts and container image **IDs** from inspect.
2. Back up configuration and record hashes, images, commands, mounts, original restart
   policies and all affected sites' baseline. Full inspect/config output can contain
   secrets: retain it privately with restrictive permissions, never paste it into tickets.
3. Check queued and in-progress ARQ jobs. Drain the worker and avoid new submissions in
   the approved window. An empty queue at audit time is not a guarantee for later.
4. Verify database backups and restore procedure; record named PostgreSQL/media volumes.
5. Find the Redis mount whose destination is `/data`:

   ```bash
   docker inspect --format '{{json .Mounts}}' YOUR_SLIDE_REDIS_CONTAINER
   ```

   Export `SLIDE_REDIS_DATA_VOLUME` with that exact existing volume name. It must exist.
   If `/data` is a bind mount, stop and adapt the overlay; do not substitute a new volume.
   The external-volume declaration deliberately fails if the name is missing/not found.
6. In the project directory validate the merged configuration without printing secrets:

   ```bash
   docker compose --env-file .env.prod -f docker-compose.prod.yml \
     -f deploy/compose.slide-io.yml config --quiet
   ```

   Use the actual environment file and **all existing** overlays if your install differs.
   Merely passing this syntax check does not verify credentials, mounts or backup validity.

## Application after approval

Pin existing images; use `--no-build --pull never --no-deps`, naming **one approved service**
at a time. Do not run unqualified `up`, `down`, `--renew-anon-volumes`, `--remove-orphans`,
volume removal, daemon restart or global prune. Check service readiness after every step.
For PostgreSQL/Redis maintenance, coordinate API/worker downtime explicitly; do not let
requests continue against an unavailable database and describe that as zero downtime.

API recreation may change its container IP. A gateway with a static resolved upstream may
need a separately validated **graceful reload** to resolve the new address. Preserve its
current configuration including unrelated sites, existing API routes, TLS, networks and
HTTPS upstream certificate checks. Reloading is not sufficient to change Docker logging.

Do not replace the live shared gateway configuration with a repository example. Other
projects may have inserted additional routes. Single-file bind mounts also require care:
verify the configuration inside the running container, not only the host file.

The shared-gateway overlay is intentionally separate. Never include it implicitly in
application maintenance. Recreating that container needs approval for the cross-site impact.

## Verification and rollback

- Compare actual `HostConfig.LogConfig`, `RestartPolicy`, `Mounts`, image IDs and resource
  parameters against the approved plan. The Redis `/data` volume must remain the same.
- Check API health **body**, PostgreSQL/Redis health and queue recovery, not only HTTP 200.
- Verify the Slide login page, API and the other sites' read-only public pages. No customer
  data mutation is necessary for this smoke test.
- Keep sampling after maintenance; short idle success is not proof that the incident cannot recur.
- Roll back only affected services using saved image IDs and exact original configuration
  and mounts. Preserve the Redis external-volume pin during rollback. Recheck gateway DNS
  after API rollback. Restoring container configuration is not a database restore.
- Removing an override file does not revert the running container; reverting its log
  settings requires another approved recreation. Never truncate Docker-managed log files.

## Favicon regression

Slide explicitly declares a transparent SVG favicon. This avoids a browser falling back to
the domain-root favicon belonging to another app. The home-screen touch icon is separate.

```bash
cd frontend
node scripts/check-favicon.mjs
npm run build
node scripts/check-favicon.mjs index.html dist/index.html
npm run preview -- --host 127.0.0.1 --port 39174 --base=/slide-report-studio/
```

Test login-page navigation/reload at the production base path in a browser, decode the
declared SVG, and check that the old favicon is not requested. An index-only deployment
must preserve existing hashed JS/CSS references and have a private rollback copy.

## References

- [Docker logging configuration](https://docs.docker.com/engine/logging/configure/): existing containers need recreation for new logging options; non-blocking buffers can drop messages.
- [Docker Compose up](https://docs.docker.com/reference/cli/docker/compose/up/): per-service recreation and anonymous-volume behavior.
- [Compose external volumes](https://docs.docker.com/reference/compose-file/volumes/): use an existing volume rather than silently creating one.
