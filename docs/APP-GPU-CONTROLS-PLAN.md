# App GPU controls and 24-hour activity plan

**Status:** In progress, 2026-11-26. Initial source implementation covers profiles, launch, and minute observations; hardware and runtime-adapter qualification remain open.
**Owner:** Unassigned
**Source baseline:** repository commit `b7a1150`, with uncommitted app rename and redraw changes in the working tree.
**Outcome:** From an Apps tab, a user can save Ollama and InvokeAI launch profiles, select the NVIDIA GPU each profile sees, launch both, and check whether each actually worked overnight.

## What the switch can do

`CUDA_VISIBLE_DEVICES` restricts the CUDA devices visible to a process **when it starts**. Store and pass a GPU UUID rather than an index, since indices can change. [NVIDIA CUDA guide](https://docs.nvidia.com/cuda/cuda-programming-guide/05-appendices/environment-variables.html), [Ollama GPU selection](https://docs.ollama.com/gpu).

The Apps tab should call this **“GPU for next launch”**, with a **Launch** button. A switch alone cannot redirect an already running program or guarantee that an arbitrary EXE will honor CUDA settings. A separately started Ollama server must be stopped and relaunched under the chosen environment before the profile applies. This is application-level device selection, not an operating-system permission boundary.

InvokeAI also has its own `generation_devices` setting. With `CUDA_VISIBLE_DEVICES` set to one UUID, InvokeAI's `cuda:0` refers to that visible card, even if its physical NVIDIA index is 1. The profile editor must show both physical UUID and effective in-process index to avoid a misleading GPU 0/1 display. [InvokeAI configuration](https://invoke-ai.github.io/InvokeAI-7/configuration/invokeai-yaml/).

GitHub Desktop can appear as a process in an activity list, but this plan does not assume it runs CUDA inference or has tokens to count. A generic EXE profile may launch successfully without obeying the GPU selection. The UI must report that as **unverified** rather than **restricted**.

## First-release journey

1. Open **Apps** and select **Add app**. Browse to an installed `.exe`, or choose a guided Ollama/InvokeAI profile. The editor shows the path, working directory, optional arguments, and detected GPUs by name and UUID.
2. Select **GPU 0** for Ollama and **GPU 1** for InvokeAI, using physical labels backed by UUIDs. Save profiles. If the selected GPU disappeared, disable Launch and ask for a new selection.
3. Launch each from the tab. Show **Launched here**, **Already running elsewhere**, **Exited**, or **Launch failed**. Show the effective environment and selected physical GPU before launch. Never silently stop or restart an existing process.
4. Return in the morning. Each card shows last observed activity, process uptime, and a 24-hour timeline with collection gaps. Show per-process GPU observations only when the platform supplies them; otherwise show device-level activity without attributing it to a specific app.
5. For a connected runtime adapter, show its own measured work: Ollama input/output tokens and request count; InvokeAI completed images or jobs only after its data source is validated. Label partial coverage when calls bypass the adapter.

## Requirements

| ID | Priority | Requirement | Acceptance check | Owner | Dependency |
| --- | --- | --- | --- | --- | --- |
| P-01 | Must | Add an Apps tab with a file picker for local `.exe` files and saved profiles. | A selected EXE path survives restart; missing paths show a repair action. | Unassigned | None |
| P-02 | Must | Bind GPU choices to NVIDIA UUIDs. | Two same-model GPUs remain correctly assigned after GPU enumeration order changes. | Unassigned | P-01 |
| P-03 | Must | Launch supported profiles with a child-process environment containing only the selected CUDA GPU UUID. | A test child sees the expected variable; a two-GPU hardware check confirms Ollama and InvokeAI run on different cards. | Unassigned | P-02 |
| P-04 | Must | Distinguish managed, external, exited, and failed processes. | An already running Ollama server is flagged as external; changing the switch does not claim to move it. | Unassigned | P-03 |
| P-05 | Must | Record a bounded 24-hour activity history with explicit gaps. | A restart restores the timeline; sleep, app closure, and collector failure show unknown intervals. | Unassigned | P-04 |
| P-06 | Must | Show provenance and availability for every number. | Device-wide GPU activity is never labeled as per-app utilization; unavailable WDDM process memory displays “Unavailable.” | Unassigned | P-05 |
| P-07 | Should | Add Ollama request accounting through an opt-in local integration. | For requests routed through it, 24-hour input/output token and request totals equal final Ollama API usage fields; bypassed traffic is labeled uncounted. | Unassigned | P-05 |
| P-08 | Should | Add an InvokeAI completion counter through a versioned, read-only adapter. | On a supported InvokeAI version, completed outputs match the adapter source; unsupported versions show unavailable rather than zero. | Unassigned | P-05 |
| P-09 | Must | Make the tab usable with keyboard and visible status text. | Browse, GPU selection, save, launch, and error recovery work without a mouse; color is not the only status cue. | Unassigned | P-01 |

## Implementation sequence

1. **Feasibility spike on the target dual-GPU Windows PC.** Record `nvidia-smi -L` UUIDs and driver mode. Launch Ollama and InvokeAI under a single selected UUID in isolation. Check whether each installation is an EXE, a service/tray process, or a launcher that starts children. Verify physical device placement and what process telemetry Windows exposes. Do this before promising a generic EXE guarantee.
2. **Profiles and launcher.** Add a small versioned profile store under the existing data directory, separate from the current `preferences.py` schema. Keep canonical EXE path, arguments, working directory, selected UUIDs, and adapter type. Use `subprocess.Popen` with an argument list and `shell=False`; never build a shell command from user text. Track PID plus process creation time and child processes to avoid PID reuse. Check for an existing server before launching a duplicate. Keep app-specific launch logic behind adapters.
3. **Apps tab.** Add Browse, profile list, physical GPU selector, Save, Launch, and live status. A disabled or unsupported CUDA profile states why. Preserve the existing Live/Replay/System pages and redraw pipeline.
4. **Activity store.** Add a bounded, separate SQLite table for process observations and adapter events. Aggregate a minute-level 24-hour timeline; mark collector downtime as unknown. NVIDIA process queries can identify active compute PIDs, but NVIDIA documents per-process memory as unavailable under Windows WDDM. Do not infer per-app work from a device-wide utilization curve. [NVIDIA SMI reference](https://docs.nvidia.com/deploy/nvidia-smi/).
5. **Runtime details.** Ollama returns `prompt_eval_count`, `eval_count`, durations, and other metrics in responses; streaming usage arrives in the final chunk. To total all requests reliably, the monitor must see those responses, such as through an opt-in local endpoint/proxy used by the caller. It cannot reconstruct historical token totals from GPU usage alone. [Ollama usage API](https://docs.ollama.com/api/usage). Validate an InvokeAI read-only API/database source before promising image/job totals; otherwise ship only process and GPU observations for it.
6. **Qualification.** Unit-test profile validation, UUID mapping, subprocess environment, PID reuse, missing EXE/GPU, and history gap logic. Add a Windows packaged smoke test for file selection and a fake child EXE. On actual two-GPU hardware, test Ollama/InvokeAI together overnight, sleep/resume, restart, crash, and running-server conflicts. Existing GitHub Actions is the CI system; there is no `.circleci/config.yml`, so use its Windows matrix and artifact gates rather than adding a second CI service without a concrete need.

## Experience states

| State | Apps tab treatment |
| --- | --- |
| No profiles | One clear Add app action and a two-GPU example. |
| Missing executable or GPU | Keep profile, disable launch, offer Browse or GPU reassignment. |
| App already running outside monitor | “Running elsewhere; selection applies only after a managed restart.” |
| CUDA unsupported or ignored | “GPU assignment unverified” plus observed process/device information. |
| No inference adapter | Show runtime and observed GPU activity; token/image counts say “Unavailable.” |
| Monitor was closed overnight | Timeline marks the closed interval as unknown, not idle. |
| Telemetry unavailable | Show last successful observation, reason, and retry action. |

## Measures and next decision

| Measure | Method | Baseline | Proposed target |
| --- | --- | --- | --- |
| Correct placement | Two-GPU physical run with both managed apps active | Unknown | Both observed on selected cards in the supported setup |
| Overnight visibility | 24-hour timeline with known/unknown intervals and last activity | Unknown | No fabricated zeroes during collection gaps |
| Launch reliability | Managed launch attempts and explicit failure states | Unknown | Every attempt ends in launched, external, or actionable error state |
| Token accuracy | Compare adapter totals with captured final Ollama responses | Unknown | Exact equality for routed completed requests |

**Highest-risk assumption:** the user's installed Ollama and InvokeAI launchers accept a child-process GPU environment and expose enough telemetry on their Windows driver configuration. Validate that with the feasibility spike. The main product decision after that spike is whether version one should ship process/GPU activity first or wait for opt-in runtime accounting.

## Implementation checkpoint · 2026-11-26

The source build now has an Apps tab, versioned `app-profiles.json`, UUID-bound GPU selection, a child-process launcher, managed/external/exited/failed states, and a separate 24-hour SQLite observation store. It displays process uptime, known/unknown minute counts, and device-wide GPU activity with explicit provenance. Missing EXE, working directory, and GPU states disable launch. Automated checks cover profile persistence, UUID mapping, the child environment, and gap storage.

Still open: target-machine dual-GPU feasibility, process child-tree tracking, Ollama request accounting, validated InvokeAI completion counts, packaged Windows GUI smoke testing, and overnight qualification. The generic EXE assignment remains unverified. See [Apps documentation](GPU-APPS.md).

The feasibility inventory on this machine found two RTX 3090s and one RTX 4070, each with a distinct UUID and WDDM driver mode. `ollama.exe` is installed; no InvokeAI command was found on `PATH`. This confirms device discovery, not runtime GPU placement.

[Explore Product Plan starters in Codelit](https://codelit.io/specs)
