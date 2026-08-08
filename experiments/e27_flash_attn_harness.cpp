#include "ggml-backend.h"
#include "ggml-cpu.h"
#include "ggml.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <string>
#include <vector>

struct options {
    std::string mode = "compare";
    int64_t head_size = 128;
    int64_t query_tokens = 64;
    int64_t kv_tokens = 512;
    int64_t query_heads = 24;
    int64_t kv_heads = 8;
    int threads = 4;
    int repetitions = 7;
    int seed = 42;
    ggml_type kv_type = GGML_TYPE_F16;
    bool causal_mask = true;
};

static void usage(const char * argv0) {
    std::fprintf(stderr,
        "usage: %s [--mode compare|reference|tiled] [--head-size N] [--query-tokens N] "
        "[--kv-tokens N] [--query-heads N] [--kv-heads N] [--threads N] "
        "[--repetitions N] [--seed N] [--kv-type f16|f32] [--causal-mask 0|1]\n",
        argv0);
}

static int parse_int(const char * value, const char * name) {
    char * end = nullptr;
    const long parsed = std::strtol(value, &end, 10);
    if (!end || *end != '\0' || parsed <= 0 || parsed > INT32_MAX) {
        std::fprintf(stderr, "invalid %s: %s\n", name, value);
        std::exit(2);
    }
    return (int) parsed;
}

static bool parse_bool(const char * value, const char * name) {
    if (std::strcmp(value, "0") == 0) {
        return false;
    }
    if (std::strcmp(value, "1") == 0) {
        return true;
    }
    std::fprintf(stderr, "invalid %s: %s\n", name, value);
    std::exit(2);
}

static options parse_options(int argc, char ** argv) {
    options opts;
    for (int i = 1; i < argc; i++) {
        if (i + 1 >= argc) {
            usage(argv[0]);
            std::exit(2);
        }
        const std::string key = argv[i++];
        const char * value = argv[i];
        if (key == "--mode") {
            opts.mode = value;
        } else if (key == "--head-size") {
            opts.head_size = parse_int(value, "head size");
        } else if (key == "--query-tokens") {
            opts.query_tokens = parse_int(value, "query tokens");
        } else if (key == "--kv-tokens") {
            opts.kv_tokens = parse_int(value, "KV tokens");
        } else if (key == "--query-heads") {
            opts.query_heads = parse_int(value, "query heads");
        } else if (key == "--kv-heads") {
            opts.kv_heads = parse_int(value, "KV heads");
        } else if (key == "--threads") {
            opts.threads = parse_int(value, "threads");
        } else if (key == "--repetitions") {
            opts.repetitions = parse_int(value, "repetitions");
        } else if (key == "--seed") {
            opts.seed = parse_int(value, "seed");
        } else if (key == "--kv-type") {
            if (std::strcmp(value, "f16") == 0) {
                opts.kv_type = GGML_TYPE_F16;
            } else if (std::strcmp(value, "f32") == 0) {
                opts.kv_type = GGML_TYPE_F32;
            } else {
                std::fprintf(stderr, "invalid KV type: %s\n", value);
                std::exit(2);
            }
        } else if (key == "--causal-mask") {
            opts.causal_mask = parse_bool(value, "causal mask");
        } else {
            std::fprintf(stderr, "unknown option: %s\n", key.c_str());
            usage(argv[0]);
            std::exit(2);
        }
    }
    if (opts.mode != "compare" && opts.mode != "reference" && opts.mode != "tiled") {
        std::fprintf(stderr, "invalid mode: %s\n", opts.mode.c_str());
        std::exit(2);
    }
    if (opts.query_heads % opts.kv_heads != 0) {
        std::fprintf(stderr, "query heads must be divisible by KV heads\n");
        std::exit(2);
    }
    return opts;
}

static std::vector<float> random_f32(size_t count, std::mt19937 & rng) {
    std::uniform_real_distribution<float> distribution(-0.5f, 0.5f);
    std::vector<float> values(count);
    for (float & value : values) {
        value = distribution(rng);
    }
    return values;
}

static void set_f32_or_f16(ggml_tensor * tensor, const std::vector<float> & values) {
    if (tensor->type == GGML_TYPE_F32) {
        ggml_backend_tensor_set(tensor, values.data(), 0, values.size() * sizeof(float));
        return;
    }
    std::vector<ggml_fp16_t> converted(values.size());
    ggml_fp32_to_fp16_row(values.data(), converted.data(), (int64_t) values.size());
    ggml_backend_tensor_set(tensor, converted.data(), 0, converted.size() * sizeof(ggml_fp16_t));
}

static double percentile(std::vector<double> values, double q) {
    std::sort(values.begin(), values.end());
    const size_t index = (size_t) std::ceil(q * values.size()) - 1;
    return values[std::min(index, values.size() - 1)];
}

int main(int argc, char ** argv) {
    const options opts = parse_options(argc, argv);
    ggml_time_init();
    ggml_backend_t backend = ggml_backend_cpu_init();
    if (!backend) {
        std::fprintf(stderr, "failed to initialize CPU backend\n");
        return 1;
    }
    ggml_backend_cpu_set_n_threads(backend, opts.threads);

    ggml_init_params params = {
        8 * 1024 * 1024,
        nullptr,
        true,
    };
    ggml_context * ctx = ggml_init(params);
    if (!ctx) {
        std::fprintf(stderr, "failed to initialize ggml context\n");
        ggml_backend_free(backend);
        return 1;
    }

    ggml_tensor * q = ggml_new_tensor_4d(ctx, GGML_TYPE_F32, opts.head_size, opts.query_tokens, opts.query_heads, 1);
    ggml_tensor * k = ggml_new_tensor_4d(ctx, opts.kv_type, opts.head_size, opts.kv_tokens, opts.kv_heads, 1);
    ggml_tensor * v = ggml_new_tensor_4d(ctx, opts.kv_type, opts.head_size, opts.kv_tokens, opts.kv_heads, 1);
    ggml_tensor * mask = opts.causal_mask ? ggml_new_tensor_4d(ctx, GGML_TYPE_F16, opts.kv_tokens, opts.query_tokens, 1, 1) : nullptr;
    ggml_tensor * out = ggml_flash_attn_ext(ctx, q, k, v, mask, 1.0f / std::sqrt((float) opts.head_size), 0.0f, 0.0f);
    ggml_flash_attn_ext_set_prec(out, GGML_PREC_F32);
    ggml_cgraph * graph = ggml_new_graph_custom(ctx, 16, false);
    ggml_build_forward_expand(graph, out);

    ggml_backend_buffer_t buffer = ggml_backend_alloc_ctx_tensors(ctx, backend);
    if (!buffer) {
        std::fprintf(stderr, "failed to allocate backend buffer\n");
        ggml_free(ctx);
        ggml_backend_free(backend);
        return 1;
    }

    std::mt19937 rng((uint32_t) opts.seed);
    set_f32_or_f16(q, random_f32((size_t) ggml_nelements(q), rng));
    set_f32_or_f16(k, random_f32((size_t) ggml_nelements(k), rng));
    set_f32_or_f16(v, random_f32((size_t) ggml_nelements(v), rng));
    if (mask) {
        std::vector<float> mask_f32((size_t) ggml_nelements(mask), -INFINITY);
        const int64_t prefix = std::max<int64_t>(0, opts.kv_tokens - opts.query_tokens);
        for (int64_t tq = 0; tq < opts.query_tokens; tq++) {
            const int64_t visible = std::min(opts.kv_tokens, prefix + tq + 1);
            std::fill_n(mask_f32.data() + tq * opts.kv_tokens, visible, 0.0f);
        }
        set_f32_or_f16(mask, mask_f32);
    }

    auto compute = [&](bool use_reference) {
        ggml_backend_cpu_set_use_ref(backend, use_reference);
        const ggml_status status = ggml_backend_graph_compute(backend, graph);
        if (status != GGML_STATUS_SUCCESS) {
            std::fprintf(stderr, "graph compute failed: %s\n", ggml_status_to_string(status));
            std::exit(1);
        }
    };
    auto get_output = [&]() {
        std::vector<float> values((size_t) ggml_nelements(out));
        ggml_backend_tensor_get(out, values.data(), 0, values.size() * sizeof(float));
        return values;
    };

    if (opts.mode == "compare") {
        compute(true);
        const std::vector<float> reference = get_output();
        compute(false);
        const std::vector<float> tiled = get_output();
        double squared_error = 0.0;
        double squared_reference = 0.0;
        double max_abs_error = 0.0;
        for (size_t i = 0; i < reference.size(); i++) {
            const double error = (double) tiled[i] - reference[i];
            squared_error += error * error;
            squared_reference += (double) reference[i] * reference[i];
            max_abs_error = std::max(max_abs_error, std::abs(error));
        }
        const double nmse = squared_reference == 0.0 ? squared_error : squared_error / squared_reference;
        std::printf("{\"mode\":\"compare\",\"head_size\":%lld,\"query_tokens\":%lld,\"kv_tokens\":%lld,"
                    "\"query_heads\":%lld,\"kv_heads\":%lld,\"kv_type\":\"%s\",\"nmse\":%.12g,\"max_abs_error\":%.12g,"
                    "\"tolerance_nmse\":0.0005,\"pass\":%s}\n",
                    (long long) opts.head_size, (long long) opts.query_tokens, (long long) opts.kv_tokens,
                    (long long) opts.query_heads, (long long) opts.kv_heads, ggml_type_name(opts.kv_type),
                    nmse, max_abs_error, nmse <= 0.0005 ? "true" : "false");
    } else {
        const bool use_reference = opts.mode == "reference";
        compute(use_reference);
        std::vector<double> samples;
        samples.reserve((size_t) opts.repetitions);
        for (int i = 0; i < opts.repetitions; i++) {
            const auto start = std::chrono::steady_clock::now();
            compute(use_reference);
            const auto end = std::chrono::steady_clock::now();
            samples.push_back(std::chrono::duration<double, std::micro>(end - start).count());
        }
        const std::vector<float> values = get_output();
        double checksum = 0.0;
        for (float value : values) {
            checksum += value;
        }
        std::printf("{\"mode\":\"%s\",\"head_size\":%lld,\"query_tokens\":%lld,\"kv_tokens\":%lld,"
                    "\"query_heads\":%lld,\"kv_heads\":%lld,\"kv_type\":\"%s\",\"threads\":%d,"
                    "\"repetitions\":%d,\"median_us\":%.3f,\"p95_us\":%.3f,\"checksum\":%.12g}\n",
                    opts.mode.c_str(), (long long) opts.head_size, (long long) opts.query_tokens, (long long) opts.kv_tokens,
                    (long long) opts.query_heads, (long long) opts.kv_heads, ggml_type_name(opts.kv_type), opts.threads,
                    opts.repetitions, percentile(samples, 0.5), percentile(samples, 0.95), checksum);
    }

    ggml_backend_buffer_free(buffer);
    ggml_free(ctx);
    ggml_backend_free(backend);
    return 0;
}
