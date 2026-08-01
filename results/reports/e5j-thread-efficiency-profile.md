# E5j Arm serving thread-efficiency profile

Native run [`30677332825`](https://github.com/Arshgill01/Arm/actions/runs/30677332825)
completed the frozen 4–3–2–2–3–4 matrix on a four-core Neoverse N2. All six
fresh servers used the exact selected model and pinned KleidiAI runtime with
repacked weights, f16 K/V cache, 256-token context, 64/64 prompt batch,
automatic Flash Attention, shared-prefix caching, one slot, and one client.

## Result

No lower-thread profile cleared the frozen gates. Four threads remains the
default.

| Profile | Median throughput | Pooled median / p95 HTTP | Median server CPU seconds/request | CPU-time ratio | Throughput retention | Decision |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 4 threads | 0.9261 req/s | 1,052.9 / 1,864.9 ms | 4.2682 s | 1.0000x | 1.0000x | Retain baseline |
| 3 threads | 0.6994 req/s | 1,384.9 / 2,542.5 ms | 4.2637 s | 0.9989x | 0.7552x | Reject |
| 2 threads | 0.4739 req/s | 2,064.9 / 3,652.9 ms | 4.2102 s | 0.9864x | 0.5118x | Reject |

Three threads reduced CPU seconds per request by only 0.11%, below the required
5%, while losing 24.48% throughput. Its median and p95 latency ratios were
1.3153x and 1.3634x, outside the 1.05 ceilings. Two threads reduced CPU seconds
per request by 1.36% while losing 48.82% throughput; its median and p95 latency
ratios were 1.9612x and 1.9588x. Both candidates failed the CPU-time,
throughput, and latency gates.

Every profile reproduced the selected 23/30 prediction map in both repetitions,
with zero prediction drift, zero request failures, and prefix reuse in every
measured request. Quality therefore did not cause either rejection.

## Measurement boundary

The inference probe sampled `/proc/<llama-server-pid>/stat` after two warmups and
immediately around the 30 measured requests. Each record binds the PID written
by the workflow, retains integer user/system ticks and the 100 Hz host clock
rate, and recomputes total CPU seconds, seconds per request, and average cores
used. Model load, readiness, warmups, the Python client, metrics collection, and
shutdown are outside the interval.

The observed average server core usage was 3.9526, 2.9820, and 1.9953 for the
four-, three-, and two-thread profiles. That confirms the thread controls
changed active server parallelism while total CPU work per request remained
nearly flat.

CPU time is not energy or power. This experiment does not support an energy
savings claim.

## Validation

- both llama.cpp `--threads` and `--threads-batch` were bound in every hashed
  recipe;
- the timed outer launcher command independently bound the requested profile;
- all input hashes, model bytes, runtime commit, buffer proof, readiness, RSS,
  slots, metrics, and server exit statuses passed;
- raw CPU tick arithmetic and PID binding were independently validated for all
  six cells; and
- Python 3.10 re-ingestion reproduced the uploaded summary byte for byte at
  SHA-256
  `747b6795d42be691c07cf5aac38237095477d06149e787cc313ec2b9558c4ff7`.

The earlier run `30677290911` stopped before model download, build, or
measurement because its source proof searched for a nonexistent combined
symbol. The corrected proof binds the exact public option declarations; the
contract, inputs, order, measurements, and thresholds did not change.

See the frozen
[`E5j contract`](../../experiments/e5j_contract.json), retained
[`manifest`](../manifests/e5j-30677332825.json), and native
[`workflow`](../../.github/workflows/thread-efficiency-profile.yml).
