#include "ggml-cpu/repack.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>

static bool check_case(int nb, uint32_t seed) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_int_distribution<int> q8_dist(-100, 100);
    std::uniform_int_distribution<int> bsum_dist(-800, 800);

    std::vector<block_q4_Kx8> q4(nb);
    std::vector<block_q8_Kx4> q8(nb);
    for (int b = 0; b < nb; ++b) {
        for (int i = 0; i < 8; ++i) {
            q4[b].d[i] = 0x2800 + i * 0x40;
            q4[b].dmin[i] = 0x2400 + i * 0x40;
        }
        for (uint8_t & value : q4[b].scales) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        for (uint8_t & value : q4[b].qs) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        for (int row = 0; row < 4; ++row) {
            q8[b].d[row] = 0.001f * static_cast<float>(row + 1);
        }
        for (int8_t & value : q8[b].qs) {
            value = static_cast<int8_t>(q8_dist(rng));
        }
        for (int16_t & value : q8[b].bsums) {
            value = static_cast<int16_t>(bsum_dist(rng));
        }
    }

    std::vector<float> reference(32, 0.0f);
    std::vector<float> actual(32, 0.0f);
    ggml_gemm_q4_K_8x8_q8_K_generic(nb * QK_K, reference.data(), 8, q4.data(), q8.data(), 4, 8);
    ggml_gemm_q4_K_8x8_q8_K(nb * QK_K, actual.data(), 8, q4.data(), q8.data(), 4, 8);

    double squared_error = 0.0;
    double squared_reference = 0.0;
    double max_abs = 0.0;
    for (size_t i = 0; i < reference.size(); ++i) {
        if (!std::isfinite(reference[i]) || !std::isfinite(actual[i])) {
            std::fprintf(stderr, "non-finite output at nb=%d index=%zu\n", nb, i);
            return false;
        }
        const double error = static_cast<double>(actual[i]) - reference[i];
        squared_error += error * error;
        squared_reference += static_cast<double>(reference[i]) * reference[i];
        max_abs = std::max(max_abs, std::abs(error));
    }
    const double nmse = squared_error / std::max(squared_reference, 1e-30);
    std::printf("nb=%d seed=%u nmse=%.12g max_abs=%.12g\n", nb, seed, nmse, max_abs);
    return nmse <= 5e-4;
}

int main() {
    bool ok = true;
    for (int nb : {1, 2, 3, 12, 36}) {
        for (uint32_t seed : {1U, 17U, 1234567U}) {
            ok = check_case(nb, seed) && ok;
        }
    }
    return ok ? 0 : 1;
}
