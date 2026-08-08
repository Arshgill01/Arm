#include "ggml-cpu/repack.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <random>
#include <utility>
#include <vector>

namespace {

struct buffers {
    std::vector<block_q4_Kx8> q4;
    std::vector<block_q8_K> q8;
};

buffers make_buffers(int n, int nc, uint32_t seed) {
    const int nb = n / QK_K;
    buffers result{
        std::vector<block_q4_Kx8>(static_cast<size_t>(nc / 8) * nb),
        std::vector<block_q8_K>(nb),
    };

    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_int_distribution<int> q8_dist(-100, 100);
    std::uniform_int_distribution<int> bsum_dist(-800, 800);
    for (block_q4_Kx8 & block : result.q4) {
        for (int column = 0; column < 8; ++column) {
            block.d[column] = static_cast<uint16_t>(0x2800 + column * 0x40);
            block.dmin[column] = static_cast<uint16_t>(0x2400 + column * 0x40);
        }
        for (uint8_t & value : block.scales) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        for (uint8_t & value : block.qs) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
    }
    for (block_q8_K & block : result.q8) {
        block.d = 0.001f * static_cast<float>(1 + seed % 7);
        for (int8_t & value : block.qs) {
            value = static_cast<int8_t>(q8_dist(rng));
        }
        for (int16_t & value : block.bsums) {
            value = static_cast<int16_t>(bsum_dist(rng));
        }
    }
    return result;
}

bool check_case(int n, int nc, uint32_t seed) {
    buffers input = make_buffers(n, nc, seed);
    std::vector<float> reference(nc, 0.0f);
    std::vector<float> actual(nc, 0.0f);

    ggml_gemv_q4_K_8x8_q8_K_generic(
        n, reference.data(), nc, input.q4.data(), input.q8.data(), 1, nc);
#if defined(__aarch64__)
    ggml_gemv_q4_K_8x8_q8_K(
        n, actual.data(), nc, input.q4.data(), input.q8.data(), 1, nc);
#else
    // The public symbol selects a different packed x86 kernel. Local runs only
    // validate harness construction; native AArch64 runs exercise the target.
    ggml_gemv_q4_K_8x8_q8_K_generic(
        n, actual.data(), nc, input.q4.data(), input.q8.data(), 1, nc);
#endif

    double squared_error = 0.0;
    double squared_reference = 0.0;
    double max_abs = 0.0;
    for (size_t index = 0; index < reference.size(); ++index) {
        if (!std::isfinite(reference[index]) || !std::isfinite(actual[index])) {
            std::fprintf(stderr, "non-finite output at n=%d nc=%d seed=%u index=%zu\n",
                         n, nc, seed, index);
            return false;
        }
        const double error = static_cast<double>(actual[index]) - reference[index];
        squared_error += error * error;
        squared_reference += static_cast<double>(reference[index]) * reference[index];
        max_abs = std::max(max_abs, std::abs(error));
    }
    const double nmse = squared_error / std::max(squared_reference, 1e-30);
    std::printf("n=%d nc=%d seed=%u nmse=%.12g max_abs=%.12g\n",
                n, nc, seed, nmse, max_abs);
    return nmse <= 5e-4;
}

}  // namespace

int main() {
    bool ok = true;
    for (const auto [n, nc] : {
             std::pair{256, 8},
             std::pair{512, 16},
             std::pair{3072, 72},
             std::pair{9216, 24},
         }) {
        for (uint32_t seed : {1U, 17U, 1234567U}) {
            ok = check_case(n, nc, seed) && ok;
        }
    }
    return ok ? 0 : 1;
}
