#include "ggml-alloc.h"
#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"
#include "repack.h"

#include <algorithm>
#include <chrono>
#include <cinttypes>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

struct options {
    int64_t n_embd   = 512;
    int64_t n_ff     = 1024;
    int64_t n_tokens = 1;
    int     n_threads = 4;
    int     repetitions = 3;
    bool    supported_names = true;
    std::string output_path;
};

static void fail(const char * message) {
    std::fprintf(stderr, "%s\n", message);
    std::exit(1);
}

static int64_t parse_i64(const char * value, const char * option) {
    char * end = nullptr;
    const long long parsed = std::strtoll(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0) {
        std::fprintf(stderr, "invalid %s: %s\n", option, value);
        std::exit(2);
    }
    return parsed;
}

static options parse_options(int argc, char ** argv) {
    options result;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--unsupported-names") {
            result.supported_names = false;
            continue;
        }
        if (i + 1 >= argc) {
            fail("missing option value");
        }
        const char * value = argv[++i];
        if (arg == "--n-embd") {
            result.n_embd = parse_i64(value, "n-embd");
        } else if (arg == "--n-ff") {
            result.n_ff = parse_i64(value, "n-ff");
        } else if (arg == "--n-tokens") {
            result.n_tokens = parse_i64(value, "n-tokens");
        } else if (arg == "--threads") {
            result.n_threads = parse_i64(value, "threads");
        } else if (arg == "--repetitions") {
            result.repetitions = parse_i64(value, "repetitions");
        } else if (arg == "--output") {
            result.output_path = value;
        } else {
            std::fprintf(stderr, "unknown option: %s\n", arg.c_str());
            std::exit(2);
        }
    }
    if (result.n_embd % 256 != 0 || result.n_ff % 256 != 0) {
        fail("n-embd and n-ff must be multiples of 256");
    }
    return result;
}

static std::vector<float> make_values(size_t count, float scale, float phase) {
    std::vector<float> values(count);
    for (size_t i = 0; i < count; ++i) {
        values[i] = scale * std::sin(phase + static_cast<float>(i % 8191) * 0.017f);
    }
    return values;
}

static std::vector<uint8_t> quantize(enum ggml_type type, const std::vector<float> & values, int64_t nrows, int64_t n_per_row) {
    std::vector<uint8_t> result(ggml_row_size(type, n_per_row) * nrows);
    const size_t written = ggml_quantize_chunk(type, values.data(), result.data(), 0, nrows, n_per_row, nullptr);
    if (written != result.size()) {
        fail("quantized byte count differs");
    }
    return result;
}

static uint64_t hash_floats(const std::vector<float> & values) {
    uint64_t hash = 1469598103934665603ULL;
    const uint8_t * bytes = reinterpret_cast<const uint8_t *>(values.data());
    for (size_t i = 0; i < values.size() * sizeof(float); ++i) {
        hash ^= bytes[i];
        hash *= 1099511628211ULL;
    }
    return hash;
}

int main(int argc, char ** argv) {
    const options opts = parse_options(argc, argv);
    const size_t metadata_size = ggml_tensor_overhead() * 16 + ggml_graph_overhead();
    const ggml_init_params context_params = {
        /* .mem_size   = */ metadata_size,
        /* .mem_buffer = */ nullptr,
        /* .no_alloc   = */ true,
    };

    ggml_context * ctx_weights = ggml_init(context_params);
    ggml_context * ctx_graph   = ggml_init(context_params);
    if (!ctx_weights || !ctx_graph) {
        fail("ggml context allocation failed");
    }

    ggml_tensor * gate_weight = ggml_new_tensor_2d(ctx_weights, GGML_TYPE_Q4_K, opts.n_embd, opts.n_ff);
    ggml_tensor * up_weight   = ggml_new_tensor_2d(ctx_weights, GGML_TYPE_Q4_K, opts.n_embd, opts.n_ff);
    ggml_tensor * down_weight = ggml_new_tensor_2d(ctx_weights, GGML_TYPE_Q4_K, opts.n_ff, opts.n_embd);
    ggml_set_name(gate_weight, opts.supported_names ? "blk.0.ffn_gate.weight" : "blk.0.attn_q.weight");
    ggml_set_name(up_weight, opts.supported_names ? "blk.0.ffn_up.weight" : "blk.0.attn_k.weight");
    ggml_set_name(down_weight, "blk.0.ffn_down.weight");

    ggml_backend_buffer_t weight_buffer = ggml_backend_alloc_ctx_tensors_from_buft(
            ctx_weights, ggml_backend_cpu_repack_buffer_type());
    if (!weight_buffer) {
        fail("repack weight allocation failed");
    }
    ggml_backend_buffer_set_usage(weight_buffer, GGML_BACKEND_BUFFER_USAGE_WEIGHTS);

    const std::vector<float> gate_values = make_values(opts.n_embd * opts.n_ff, 0.075f, 0.11f);
    const std::vector<float> up_values   = make_values(opts.n_embd * opts.n_ff, 0.070f, 0.29f);
    const std::vector<float> down_values = make_values(opts.n_ff * opts.n_embd, 0.055f, 0.47f);
    const std::vector<uint8_t> gate_quantized = quantize(GGML_TYPE_Q4_K, gate_values, opts.n_ff, opts.n_embd);
    const std::vector<uint8_t> up_quantized   = quantize(GGML_TYPE_Q4_K, up_values, opts.n_ff, opts.n_embd);
    const std::vector<uint8_t> down_quantized = quantize(GGML_TYPE_Q4_K, down_values, opts.n_embd, opts.n_ff);
    ggml_backend_tensor_set(gate_weight, gate_quantized.data(), 0, gate_quantized.size());
    ggml_backend_tensor_set(up_weight, up_quantized.data(), 0, up_quantized.size());
    ggml_backend_tensor_set(down_weight, down_quantized.data(), 0, down_quantized.size());

    ggml_tensor * input      = ggml_new_tensor_2d(ctx_graph, GGML_TYPE_F32, opts.n_embd, opts.n_tokens);
    ggml_tensor * gate       = ggml_mul_mat(ctx_graph, gate_weight, input);
    ggml_tensor * up         = ggml_mul_mat(ctx_graph, up_weight, input);
    ggml_tensor * activation = ggml_swiglu_split(ctx_graph, gate, up);
    ggml_tensor * output     = ggml_mul_mat(ctx_graph, down_weight, activation);
    ggml_set_name(input, "ffn_input-0");
    ggml_set_name(gate, "ffn_gate-0");
    ggml_set_name(up, "ffn_up-0");
    ggml_set_name(activation, "ffn_swiglu-0");
    ggml_set_name(output, "ffn_down-0");
    ggml_set_output(output);

    ggml_backend_t backend = ggml_backend_cpu_init();
    if (!backend) {
        fail("CPU backend initialization failed");
    }
    ggml_backend_cpu_set_n_threads(backend, opts.n_threads);
    ggml_backend_buffer_t graph_buffer = ggml_backend_alloc_ctx_tensors(ctx_graph, backend);
    if (!graph_buffer) {
        fail("graph tensor allocation failed");
    }

    ggml_cgraph * graph = ggml_new_graph(ctx_graph);
    ggml_build_forward_expand(graph, output);
    std::printf("nodes=");
    for (int i = 0; i < ggml_graph_n_nodes(graph); ++i) {
        std::printf("%s%s", i ? "," : "", ggml_get_name(ggml_graph_node(graph, i)));
    }
    std::printf("\n");

    const std::vector<float> input_values = make_values(opts.n_embd * opts.n_tokens, 0.5f, 0.73f);
    ggml_backend_tensor_set(input, input_values.data(), 0, input_values.size() * sizeof(float));

    const float sentinel = std::numeric_limits<float>::quiet_NaN();
    std::vector<float> intermediate(opts.n_ff * opts.n_tokens, sentinel);
    ggml_backend_tensor_set(gate, intermediate.data(), 0, intermediate.size() * sizeof(float));
    ggml_backend_tensor_set(up, intermediate.data(), 0, intermediate.size() * sizeof(float));

    if (ggml_backend_graph_compute(backend, graph) != GGML_STATUS_SUCCESS) {
        fail("warmup graph compute failed");
    }

    ggml_backend_tensor_get(gate, intermediate.data(), 0, intermediate.size() * sizeof(float));
    const size_t gate_written = std::count_if(intermediate.begin(), intermediate.end(), [](float value) { return !std::isnan(value); });
    ggml_backend_tensor_get(up, intermediate.data(), 0, intermediate.size() * sizeof(float));
    const size_t up_written = std::count_if(intermediate.begin(), intermediate.end(), [](float value) { return !std::isnan(value); });

    std::vector<double> times_ms;
    for (int repetition = 0; repetition < opts.repetitions; ++repetition) {
        const auto start = std::chrono::steady_clock::now();
        if (ggml_backend_graph_compute(backend, graph) != GGML_STATUS_SUCCESS) {
            fail("timed graph compute failed");
        }
        const auto end = std::chrono::steady_clock::now();
        times_ms.push_back(std::chrono::duration<double, std::milli>(end - start).count());
    }
    std::sort(times_ms.begin(), times_ms.end());

    std::vector<float> output_values(opts.n_embd * opts.n_tokens);
    ggml_backend_tensor_get(output, output_values.data(), 0, output_values.size() * sizeof(float));
    if (!opts.output_path.empty()) {
        std::ofstream stream(opts.output_path, std::ios::binary);
        stream.write(reinterpret_cast<const char *>(output_values.data()), output_values.size() * sizeof(float));
        if (!stream) {
            fail("output write failed");
        }
    }

    const size_t full_intermediate_bytes = 2 * opts.n_ff * opts.n_tokens * sizeof(float);
    const size_t written_intermediate_bytes = (gate_written + up_written) * sizeof(float);
    std::printf(
            "n_embd=%" PRId64 " n_ff=%" PRId64 " n_tokens=%" PRId64 " threads=%d repetitions=%d\n"
            "gate_written=%zu up_written=%zu full_intermediate_bytes=%zu written_intermediate_bytes=%zu saved_bytes=%zu\n"
            "median_ms=%.6f output_hash=%016" PRIx64 " output_values=%zu\n",
            opts.n_embd, opts.n_ff, opts.n_tokens, opts.n_threads, opts.repetitions,
            gate_written, up_written, full_intermediate_bytes, written_intermediate_bytes,
            full_intermediate_bytes - std::min(full_intermediate_bytes, written_intermediate_bytes),
            times_ms[times_ms.size() / 2], hash_floats(output_values), output_values.size());

    ggml_backend_buffer_free(graph_buffer);
    ggml_backend_free(backend);
    ggml_backend_buffer_free(weight_buffer);
    ggml_free(ctx_graph);
    ggml_free(ctx_weights);
    ggml_quantize_free();
    return 0;
}
