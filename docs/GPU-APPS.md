# Apps tab: launch profiles and activity

The Apps tab is available in current source builds. It saves profiles in `%LOCALAPPDATA%\GPU Live Graphs\app-profiles.json`, separately from graph preferences. Each profile contains an executable path, working directory, arguments, app type, and a physical NVIDIA GPU UUID. The display shows both the physical GPU index and UUID. Inside a CUDA process restricted to one visible GPU, that card is normally `cuda:0`.

## Set up and launch

1. Open **Apps** and select **Add app**. Use **Browse** to choose an installed `.exe`.
2. Enter a name, working directory, and optional command arguments. Choose **Generic EXE**, **Ollama**, or **InvokeAI**.
3. Choose the physical GPU and select **Save profile**. The selection stays bound to its UUID if driver enumeration order changes.
4. Select **Launch**. The monitor starts the EXE with `CUDA_VISIBLE_DEVICES` set to that UUID. The effective value appears on the card. A missing EXE, directory, or GPU disables launch and explains what to repair.

The monitor does not stop or redirect a running process. For known Ollama/InvokeAI process names, an existing server is reported as **Already running elsewhere** and launch is disabled. A generic EXE may ignore CUDA settings or start another process that does; its GPU assignment remains **unverified**. InvokeAI may also need its own `generation_devices` configuration. This setting is application level selection, not an operating system permission boundary.

## Activity and limits

While the monitor is open and NVIDIA readings arrive, it records one observation per profile per minute in `app-activity.sqlite3`. The Apps card reports observed process state, uptime, the latest observed time, and known versus unknown minutes over 24 hours. A blue/gray timeline distinguishes observed from unknown minutes. Missing minutes, including monitor closure, are **unknown**. The GPU utilization number is explicitly **device-wide** and is not attributed to the app. Per-process WDDM memory, tokens, images, and job totals show **Unavailable**.

This is an initial process and device observation view. It does not yet include the opt-in Ollama request adapter or a validated InvokeAI completion adapter. The app has not been qualified with two physical GPUs or overnight Ollama/InvokeAI workloads. See the [implementation plan](APP-GPU-CONTROLS-PLAN.md) for those checks.
