#include "ggml-cpu/repack.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <vector>

int main(int argc, char ** argv) {
    if (argc != 5) {
        std::fprintf(stderr, "usage: %s N NR NC REPS\n", argv[0]);
        return 2;
    }
    const int n = std::atoi(argv[1]);
    const int nr = std::atoi(argv[2]);
    const int nc = std::atoi(argv[3]);
    const int reps = std::atoi(argv[4]);
    if (n % QK_K != 0 || nr % 4 != 0 || nc % 8 != 0 || reps < 1) {
        return 2;
    }

    const int nb = n / QK_K;
    std::vector<block_q4_Kx8> q4(static_cast<size_t>(nc / 8) * nb);
    std::vector<block_q8_Kx4> q8(static_cast<size_t>(nr / 4) * nb);
    std::vector<float> output(static_cast<size_t>(nr) * nc);
    std::mt19937 rng(1234567);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_int_distribution<int> q8_dist(-100, 100);
    std::uniform_int_distribution<int> bsum_dist(-800, 800);
    for (block_q4_Kx8 & block : q4) {
        for (int i = 0; i < 8; ++i) {
            block.d[i] = 0x2800 + i * 0x40;
            block.dmin[i] = 0x2400 + i * 0x40;
        }
        for (uint8_t & value : block.scales) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        for (uint8_t & value : block.qs) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
    }
    for (block_q8_Kx4 & block : q8) {
        for (int row = 0; row < 4; ++row) {
            block.d[row] = 0.001f * static_cast<float>(row + 1);
        }
        for (int8_t & value : block.qs) {
            value = static_cast<int8_t>(q8_dist(rng));
        }
        for (int16_t & value : block.bsums) {
            value = static_cast<int16_t>(bsum_dist(rng));
        }
    }

    ggml_gemm_q4_K_8x8_q8_K(n, output.data(), nc, q4.data(), q8.data(), nr, nc);
    std::vector<double> elapsed_ms;
    elapsed_ms.reserve(reps);
    for (int rep = 0; rep < reps; ++rep) {
        const auto start = std::chrono::steady_clock::now();
        ggml_gemm_q4_K_8x8_q8_K(n, output.data(), nc, q4.data(), q8.data(), nr, nc);
        const auto end = std::chrono::steady_clock::now();
        elapsed_ms.push_back(std::chrono::duration<double, std::milli>(end - start).count());
    }
    std::sort(elapsed_ms.begin(), elapsed_ms.end());
    double checksum = 0.0;
    for (float value : output) {
        checksum += value;
    }
    const double median_ms = elapsed_ms[elapsed_ms.size() / 2];
    const double gops = (2.0 * n * nr * nc) / (median_ms * 1.0e6);
    std::printf("n=%d nr=%d nc=%d reps=%d median_ms=%.6f gops=%.6f checksum=%.12g samples_ms=",
                n, nr, nc, reps, median_ms, gops, checksum);
    for (double value : elapsed_ms) {
        std::printf("%.6f,", value);
    }
    std::printf("\n");
    return 0;
}
