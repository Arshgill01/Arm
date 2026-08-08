#include "ggml-cpu/repack.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <vector>

int main(int argc, char ** argv) {
    if (argc != 4) {
        std::fprintf(stderr, "usage: %s N NC REPS\n", argv[0]);
        return 2;
    }
    const int n = std::atoi(argv[1]);
    const int nc = std::atoi(argv[2]);
    const int reps = std::atoi(argv[3]);
    if (n <= 0 || n % QK_K != 0 || nc <= 0 || nc % 8 != 0 || reps < 1) {
        return 2;
    }

    const int nb = n / QK_K;
    std::vector<block_q4_Kx8> q4(static_cast<size_t>(nc / 8) * nb);
    std::vector<block_q8_K> q8(nb);
    std::vector<float> output(nc, 0.0f);
    std::mt19937 rng(1234567);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_int_distribution<int> q8_dist(-100, 100);
    std::uniform_int_distribution<int> bsum_dist(-800, 800);
    for (block_q4_Kx8 & block : q4) {
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
    for (block_q8_K & block : q8) {
        block.d = 0.001f;
        for (int8_t & value : block.qs) {
            value = static_cast<int8_t>(q8_dist(rng));
        }
        for (int16_t & value : block.bsums) {
            value = static_cast<int16_t>(bsum_dist(rng));
        }
    }

    ggml_gemv_q4_K_8x8_q8_K(n, output.data(), nc, q4.data(), q8.data(), 1, nc);
    std::vector<double> elapsed_us;
    elapsed_us.reserve(reps);
    for (int rep = 0; rep < reps; ++rep) {
        const auto start = std::chrono::steady_clock::now();
        ggml_gemv_q4_K_8x8_q8_K(n, output.data(), nc, q4.data(), q8.data(), 1, nc);
        const auto end = std::chrono::steady_clock::now();
        elapsed_us.push_back(
            std::chrono::duration<double, std::micro>(end - start).count());
    }
    std::sort(elapsed_us.begin(), elapsed_us.end());

    double checksum = 0.0;
    for (float value : output) {
        checksum += value;
    }
    const double median_us = elapsed_us[elapsed_us.size() / 2];
    const double gops = (2.0 * n * nc) / (median_us * 1.0e3);
    std::printf("n=%d nc=%d reps=%d median_us=%.6f gops=%.6f checksum=%.12g samples_us=",
                n, nc, reps, median_us, gops, checksum);
    for (double value : elapsed_us) {
        std::printf("%.6f,", value);
    }
    std::printf("\n");
    return 0;
}
