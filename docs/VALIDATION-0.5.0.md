# 0.5.0 verification record

## Automated checks

- The local suite covers the original controls and new history/preferences behavior, including transient I/O recovery. The final workflow result records the release's complete test run.
- A hosted Python 3.11 run exposed a timeout in an fsync-heavy burst test. The check now uses fewer, larger records to force actual budget pressure, always closes its writer, and verifies that new samples continue after eviction. The writer reclaims space proactively before inserts rather than relying only on periodic trimming.
- History checks include restart, clock rebasing, precision, measured zero versus missing values, retention, selected-GPU CSV, a database size limit, and malformed-database preservation.
- Preference checks include interrupted replacement, invalid-file backup, future-schema preservation, GPU discovery-order changes, duplicate-card naming, detached views, and off-screen bounds.
- The frozen self-test exercises four graphs, maximize/restore, pins/popout, all three export formats, and history/preferences restart.
- Windows CI builds the portable application and installer, installs into a temporary directory, repeats installed launch checks, and uninstalls while verifying retained user data. A preview release is gated on this workflow's success.

## Short synthetic stress run

On the development Windows machine, with three synthetic GPUs and 3,600 initial records covering an hour:

- 100 resize cycles, alternating narrow and wide layouts.
- Maximize/restore every tenth cycle; detached-window open/close every fifth cycle.
- 83.7 seconds elapsed, no recorded callback failures, no unexpected exit, and no history error.
- Average measured render/update pass: 0.166 seconds; maximum 0.284 seconds in this harness.
- 3,610 samples in memory at completion, within the 4,000-sample bound.

These timings describe this harness and machine, not a general benchmark.

## Live sampling check

The NVIDIA driver detected two RTX 3090s and one RTX 4070. A 180.16-second live sampling run completed 100 narrow/wide resize cycles, periodic maximize/restore, and detached-window open/close operations. There were no recorded callback errors, no unexpected exit, and no history error. At completion, 179 live query records were in memory. The harness measured a 0.073-second average render/update pass and 0.486-second maximum; these are local test timings, not a general performance claim.

The source/frozen restart tests also cover persistence independently of this short live run. A further transient-I/O recovery check was added after the stress run; the complete suite and frozen package verification are rerun by the release workflow.

## Still open

These short checks do not establish multi-hour stability, prove the cause of the earlier abrupt exit, or cover every display layout. A complete mixed-DPI/monitor-disconnect matrix and longer workload soak remain open. No new tray, alert, or process-list feature was added in this batch.
