#include "ggml-cpu/repack.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <random>
#include <vector>

namespace {

void convert_interleave(const uint8_t * source, uint8_t * destination) {
    uint8_t columns[8][QK_K / 2];
    for (int i = 0; i < QK_K * 4 / 8; ++i) {
        const int column = i % 8;
        const int offset = (i / 8) * 8;
        std::memcpy(columns[column] + offset, source + i * 8, 8);
    }
    for (int i = 0; i < QK_K * 4 / 4; ++i) {
        const int column = i % 8;
        const int offset = (i / 8) * 4;
        std::memcpy(destination + i * 4, columns[column] + offset, 4);
    }
}

bool check_case(int nb, uint32_t seed) {
    std::mt19937 rng(seed);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_real_distribution<float> activation_dist(-2.0f, 2.0f);

    std::vector<block_q4_Kx8> q4_interleave8(nb);
    std::vector<block_q4_Kx8> q4_interleave4(nb);
    std::vector<block_q8_Kx4> q8_interleave4(nb);
    std::vector<block_q8_Kx4> q8_interleave8(nb);
    std::vector<float> activations(static_cast<size_t>(4) * nb * QK_K);
    for (int b = 0; b < nb; ++b) {
        for (int column = 0; column < 8; ++column) {
            q4_interleave8[b].d[column] = 0x2800 + column * 0x40;
            q4_interleave8[b].dmin[column] = 0x2400 + column * 0x40;
        }
        for (uint8_t & value : q4_interleave8[b].scales) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        for (uint8_t & value : q4_interleave8[b].qs) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        std::memcpy(q4_interleave4[b].d, q4_interleave8[b].d, sizeof(q4_interleave8[b].d));
        std::memcpy(q4_interleave4[b].dmin, q4_interleave8[b].dmin, sizeof(q4_interleave8[b].dmin));
        std::memcpy(q4_interleave4[b].scales, q4_interleave8[b].scales, sizeof(q4_interleave8[b].scales));
        convert_interleave(q4_interleave8[b].qs, q4_interleave4[b].qs);

    }
    for (float & value : activations) {
        value = activation_dist(rng);
    }
    ggml_quantize_mat_q8_K_4x4(
        activations.data(), q8_interleave4.data(), static_cast<int64_t>(nb) * QK_K);
    ggml_quantize_mat_q8_K_4x8(
        activations.data(), q8_interleave8.data(), static_cast<int64_t>(nb) * QK_K);

    std::vector<float> reference(32, 0.0f);
    std::vector<float> actual(32, 0.0f);
    ggml_gemm_q4_K_8x4_q8_K_generic(
        nb * QK_K, reference.data(), 8, q4_interleave4.data(), q8_interleave4.data(), 4, 8);
#if defined(E28_Q4_GEMM_Q8_4X4)
    ggml_gemm_q4_K_8x4_q8_K(
        nb * QK_K, actual.data(), 8, q4_interleave4.data(), q8_interleave4.data(), 4, 8);
#else
    ggml_gemm_q4_K_8x4_q8_K(
        nb * QK_K, actual.data(), 8, q4_interleave4.data(), q8_interleave8.data(), 4, 8);
#endif

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

}  // namespace

int main() {
    bool ok = true;
    for (int nb : {1, 2, 3, 12, 36}) {
        for (uint32_t seed : {1U, 17U, 1234567U}) {
            ok = check_case(nb, seed) && ok;
        }
    }
    return ok ? 0 : 1;
}
