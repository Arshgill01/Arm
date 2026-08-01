# Final local Arm power, governor, and cost evidence

Status: protocol design; the platform-specific collector and immutable E8a
contract remain intentionally unfrozen until the authenticated device-platform
choice is delivered.

## Evidence question

Can the already-promoted shared-prefix cache reduce energy and tariff-derived
cost per completed request on one stable local Arm device while preserving the
exact selected workload, service, and quality?

This is the cleanest remaining optimization front because E5c already showed
the largest accepted serving gain: 1.672x throughput with all 120 predictions
preserved. E8a will measure real energy for that same single change instead of
using CPU time as a power proxy or combining unrelated model, runtime, memory,
and build changes.

## Exact comparison

Both configurations must use:

- the E3f-selected Ministral Q4_K_M bytes and task order;
- the exact three-patch llama.cpp `b10216` source and OpenSSL-off E7c build;
- the E7b-bound Pareto64 launch adapter and repacked f16/256/64 four-thread,
  one-slot loopback HTTP service;
- identical model, source, build, binary, recipe, seed, output cap, client
  concurrency, ambient power source, governor/power mode, and sensor domain;
- two warm-up tasks before the measured energy window; and
- 30 measured requests per fresh-process cell.

The only comparison variable is the per-request prefix-reuse policy:

| Configuration | Request `cache_prompt` | Required mechanism evidence |
| --- | --- | --- |
| `no_cache` | `false` | every measured request reports zero cached tokens |
| `prompt_cache` | `true` | every measured request reports at least one cached token |

Keeping the exact E7c server recipe fixed matters: the baseline disables reuse
in the request, not by changing runtime source, build flags, server layout, or
deployment profile.

## Repetition and ordering

Use eight fresh-process cells in two opposite-start four-cell blocks:

1. `no_cache`, `prompt_cache`, `prompt_cache`, `no_cache`;
2. `prompt_cache`, `no_cache`, `no_cache`, `prompt_cache`.

This yields four repetitions per configuration and counterbalances start/end
and time/thermal order. The device must remain on the same power source and in
the same declared governor or power mode. Record initial/final temperature,
frequency or throttle state where exposed, and every transition or anomaly.

## Measurement boundary

The primary window starts after readiness and both warm-ups, immediately before
the 30-task probe, and stops immediately after the final response. It excludes
model download, build, model load, readiness, warm-ups, metrics collection, and
shutdown.

Prefer a monotonic cumulative energy counter. If the selected platform exposes
sampled power instead, retain every timestamped sample and integrate joules
with a documented method. The collector must record:

- sensor interface, units, domain, resolution, sampling interval, and access
  privileges;
- raw counter start/end values or every raw power sample;
- wall-clock window start/end from one monotonic clock;
- sample coverage, counter wraps/resets, missing samples, and integration
  method;
- governor/power mode and power-source state before every cell;
- available temperatures, frequencies, and throttle/thermal-pressure state;
- server PID, process CPU counters, RSS, throughput, and latency as supporting
  evidence; and
- exact host/device identity without serial numbers, credentials, or other
  private identifiers.

A 60-second idle sample before and after the matrix is useful context, but gross
joules per request is the primary result. Idle subtraction must be reported
separately and cannot replace the gross measurement.

## Frozen acceptance shape

The platform-specific contract may fill sensor-resolution and thermal fields,
but it must not weaken these common gates after observation:

- native `arm64`/`aarch64` device and exact input/source/build hashes;
- four valid cells per configuration in the declared order;
- 23/30 in every cell, zero reference drift, and zero request failures;
- zero reused tokens for every `no_cache` request and at least one for every
  `prompt_cache` request;
- one unchanged sensor domain, governor/power mode, power-source state, and
  tariff record across the comparison;
- valid monotonic energy evidence with no unexplained reset or coverage gap;
- no observed thermal-throttle event during a measured window;
- at least 1.10x repeated-median request throughput; and
- at most 0.90x repeated-median gross joules per request.

Failure of any validity gate produces a retained invalid run. Passing validity
but missing either benefit threshold produces a valid no-win. No threshold is
chosen from the observed result.

## Derived metrics and cost

For each cell:

```text
joules_per_request = measured_joules / 30
joules_per_correct_task = measured_joules / 23
energy_kwh = measured_joules / 3_600_000
cost_per_1000_requests = energy_kwh / 30 * 1000 * tariff_per_kwh
cost_per_1000_correct_tasks = energy_kwh / 23 * 1000 * tariff_per_kwh
```

The monetary calculation is allowed only when the evidence binds a currency,
rate per kWh, source, region, and effective/access date. Without that record,
E8a reports energy and a parameterized cost formula but makes no currency claim.
Local electricity cost must not be mixed with a cloud instance list price.
Hardware purchase price and amortization are separate assumptions and stay out
of the primary result unless explicitly contracted before measurement.

## Platform routing boundary

Only the selected platform will be implemented:

| Platform | Candidate evidence interfaces to verify before freezing |
| --- | --- |
| Linux Arm device | powercap/hwmon or external meter; cpufreq governor; thermal zones and throttle records |
| Apple Silicon Mac | privileged `powermetrics` domains; `pmset` power-source/mode state; thermal-pressure evidence |
| Android device | battery/power service or validated external meter; `adb` power/thermal state; governor evidence only if legitimately exposed |

Interface presence alone is not proof that a reading covers the CPU, SoC, or
whole device. The final contract must name the exact domain and bound the claim
accordingly. Root or `sudo` access is never assumed from the platform label.

## Claim boundary

A passing E8a can claim an energy and tariff-derived cost change only for the
exact selected workload, device, sensor domain, power mode, and comparison
above. A package/CPU-domain reading is not whole-device energy; a wall-meter
reading is not CPU-only energy. The result cannot establish battery life,
fleet/cloud cost, a different model/profile, or general performance per watt
without separate evidence.

## Remaining device handoff

After the authenticated platform choice arrives, the next bounded handoff must
establish the device model/OS, connection path, available privilege level,
energy sensor domain, governor/power-mode visibility, model availability, free
storage/RAM, and a tariff record if a monetary result is desired. A read-only
inventory run precedes any build or benchmark.
