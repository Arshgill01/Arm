#!/usr/bin/env bash
set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "usage: e22b_host_preflight.sh OUTPUT_DIRECTORY" >&2
  exit 2
fi
output="$1"
test ! -e "$output"
mkdir -p "$output"

date --utc --iso-8601=seconds > "$output/captured-at.txt"
uname -a > "$output/uname.txt"
lscpu > "$output/lscpu.txt"
lscpu --extended > "$output/lscpu-extended.txt"
cat /proc/cpuinfo > "$output/cpuinfo.txt"
cat /proc/meminfo > "$output/meminfo.txt"
cat /proc/stat > "$output/proc-stat.txt"
cat /proc/loadavg > "$output/loadavg.txt"
free -b > "$output/free-bytes.txt"
df -B1 / > "$output/disk-bytes.txt"
lsblk --bytes --json > "$output/lsblk.json"
systemd-detect-virt > "$output/virtualization.txt"
python3 --version > "$output/python-version.txt" 2>&1
perf --version > "$output/perf-version.txt"
git --version > "$output/git-version.txt"
curl --version > "$output/curl-version.txt"
timedatectl > "$output/timedatectl.txt"
cat /proc/sys/kernel/perf_event_paranoid > "$output/perf-event-paranoid.txt"
find /sys/bus/event_source/devices -maxdepth 1 -mindepth 1 -printf '%f\n' \
  | sort > "$output/event-sources.txt"
perf list > "$output/perf-list.txt" 2>&1

perf stat --no-big-num -x, \
  -e cycles,instructions,branches,branch-misses,cache-references,cache-misses \
  -e page-faults,minor-faults,major-faults,context-switches,cpu-migrations \
  --output "$output/perf-stat.csv" -- sleep 0.2

metadata=http://metadata.google.internal/computeMetadata/v1/instance
metadata_header='Metadata-Flavor: Google'
instance_id="$(curl --fail --silent --header "$metadata_header" "$metadata/id")"
machine_type="$(curl --fail --silent --header "$metadata_header" \
  "$metadata/machine-type")"
zone="$(curl --fail --silent --header "$metadata_header" "$metadata/zone")"
preempted="$(curl --fail --silent --header "$metadata_header" \
  "$metadata/preempted")"
maintenance_event="$(curl --fail --silent --header "$metadata_header" \
  "$metadata/maintenance-event")"

architecture="$(uname -m)"
logical_cpus="$(nproc)"
threads_per_core="$(lscpu --parse=CORE,CPU | sed '/^#/d' \
  | awk -F, '{count[$1]++} END {maximum=0; for (core in count) if (count[core] > maximum) maximum=count[core]; print maximum}')"
mem_total_kib="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
mem_total_bytes="$((mem_total_kib * 1024))"
swap_total_kib="$(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
disk_available_bytes="$(df --output=avail -B1 / | tail -1 | tr -d ' ')"
pmu_source="$(grep '^armv8_pmuv3' "$output/event-sources.txt")"

test "$architecture" = aarch64
test "$logical_cpus" = 8
test "$threads_per_core" = 1
test "$mem_total_kib" -ge 16000000
test "$swap_total_kib" = 0
test "$disk_available_bytes" -ge 20000000000
test "$(cat "$output/perf-event-paranoid.txt")" -le 1
test -n "$pmu_source"
test "$preempted" = FALSE
test "$maintenance_event" = NONE

jq -n \
  --arg instance_id "$instance_id" \
  --arg machine_type "$machine_type" \
  --arg zone "$zone" \
  --arg architecture "$architecture" \
  --arg pmu_source "$pmu_source" \
  --argjson logical_cpus "$logical_cpus" \
  --argjson threads_per_core "$threads_per_core" \
  --argjson mem_total_bytes "$mem_total_bytes" \
  --argjson swap_total_bytes "$((swap_total_kib * 1024))" \
  --argjson disk_available_bytes "$disk_available_bytes" \
  '{
    schema_version: 1,
    status: "valid_stable_axion_host_preflight",
    provider: "Google Cloud Compute Engine",
    instance_id: $instance_id,
    machine_type: $machine_type,
    zone: $zone,
    architecture: $architecture,
    cpu_model: "Neoverse-V2",
    logical_cpus: $logical_cpus,
    threads_per_core: $threads_per_core,
    mem_total_bytes: $mem_total_bytes,
    swap_total_bytes: $swap_total_bytes,
    disk_available_bytes: $disk_available_bytes,
    provisioning_model: "STANDARD",
    pmu: {
      requested_tracking_type: "standard",
      event_source: $pmu_source,
      perf_stat_available: true
    },
    preempted: false,
    maintenance_event: "NONE"
  }' > "$output/host-preflight.json"

find "$output" -type f ! -name file-inventory-sha256.txt -print0 \
  | sort -z \
  | xargs -0 sha256sum > "$output/file-inventory-sha256.txt"
jq -c '{status, machine_type, logical_cpus, mem_total_bytes, pmu}' \
  "$output/host-preflight.json"
