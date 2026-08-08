#include "ggml-cpu/repack.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <random>
#include <vector>

namespace {

struct inputs {
    std::vector<block_q4_Kx8> interleave8;
    std::vector<block_q4_Kx8> interleave4;
    std::vector<block_q4_Kx8_decoded> decoded;
    std::vector<block_q8_K> q8;
};

void decode_metadata(const uint8_t * packed, block_q4_Kx8_decoded & decoded) {
    constexpr uint32_t mask6 = 0x3f3f3f3f;
    constexpr uint32_t mask4 = 0x0f0f0f0f;
    constexpr uint32_t mask2 = 0x03030303;
    for (int subblock = 0; subblock < QK_K / 32; ++subblock) {
        uint32_t words[3];
        std::memcpy(words, packed + subblock * 12, sizeof(words));
        const uint32_t scale_words[2] = {
            words[0] & mask6,
            (words[2] & mask4) | (((words[0] >> 6) & mask2) << 4),
        };
        const uint32_t min_words[2] = {
            words[1] & mask6,
            ((words[2] >> 4) & mask4) | (((words[1] >> 6) & mask2) << 4),
        };
        std::memcpy(decoded.scales + subblock * 8, scale_words, 8);
        std::memcpy(decoded.mins + subblock * 8, min_words, 8);
    }
}

void convert_interleave(const uint8_t * source, int source_block,
                        uint8_t * destination, int destination_block) {
    uint8_t columns[8][QK_K / 2];
    for (int i = 0; i < QK_K * 4 / source_block; ++i) {
        const int column = i % 8;
        const int column_offset = (i / 8) * source_block;
        std::memcpy(columns[column] + column_offset,
                    source + i * source_block, source_block);
    }
    for (int i = 0; i < QK_K * 4 / destination_block; ++i) {
        const int column = i % 8;
        const int column_offset = (i / 8) * destination_block;
        std::memcpy(destination + i * destination_block,
                    columns[column] + column_offset, destination_block);
    }
}

inputs make_inputs(int n, int nc) {
    const int nb = n / QK_K;
    inputs result{
        std::vector<block_q4_Kx8>(static_cast<size_t>(nc / 8) * nb),
        std::vector<block_q4_Kx8>(static_cast<size_t>(nc / 8) * nb),
        std::vector<block_q4_Kx8_decoded>(static_cast<size_t>(nc / 8) * nb),
        std::vector<block_q8_K>(nb),
    };

    std::mt19937 rng(1234567);
    std::uniform_int_distribution<int> byte_dist(0, 255);
    std::uniform_int_distribution<int> q8_dist(-100, 100);
    std::uniform_int_distribution<int> bsum_dist(-800, 800);
    for (size_t index = 0; index < result.interleave8.size(); ++index) {
        block_q4_Kx8 & block8 = result.interleave8[index];
        for (int column = 0; column < 8; ++column) {
            block8.d[column] = static_cast<uint16_t>(0x2800 + column * 0x40);
            block8.dmin[column] = static_cast<uint16_t>(0x2400 + column * 0x40);
        }
        for (uint8_t & value : block8.scales) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }
        for (uint8_t & value : block8.qs) {
            value = static_cast<uint8_t>(byte_dist(rng));
        }

        block_q4_Kx8 & block4 = result.interleave4[index];
        std::memcpy(block4.d, block8.d, sizeof(block8.d));
        std::memcpy(block4.dmin, block8.dmin, sizeof(block8.dmin));
        std::memcpy(block4.scales, block8.scales, sizeof(block8.scales));
        convert_interleave(block8.qs, 8, block4.qs, 4);
        decode_metadata(block4.scales, result.decoded[index]);
    }
    for (block_q8_K & block : result.q8) {
        block.d = 0.001f;
        for (int8_t & value : block.qs) {
            value = static_cast<int8_t>(q8_dist(rng));
        }
        for (int16_t & value : block.bsums) {
            value = static_cast<int16_t>(bsum_dist(rng));
        }
    }
    return result;
}

double nmse(const std::vector<float> & reference, const std::vector<float> & actual) {
    double squared_error = 0.0;
    double squared_reference = 0.0;
    for (size_t index = 0; index < reference.size(); ++index) {
        if (!std::isfinite(reference[index]) || !std::isfinite(actual[index])) {
            return INFINITY;
        }
        const double error = static_cast<double>(actual[index]) - reference[index];
        squared_error += error * error;
        squared_reference += static_cast<double>(reference[index]) * reference[index];
    }
    return squared_error / std::max(squared_reference, 1e-30);
}

using kernel = void (*)(int, float *, size_t, const void *, const void *, int, int);

double time_call(kernel function, int n, int nc, const void * q4,
                 const void * q8, std::vector<float> & output) {
    const auto start = std::chrono::steady_clock::now();
    function(n, output.data(), nc, q4, q8, 1, nc);
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::micro>(end - start).count();
}

double median(std::vector<double> samples) {
    std::sort(samples.begin(), samples.end());
    return samples[samples.size() / 2];
}

}  // namespace

int main(int argc, char ** argv) {
    if (argc != 4) {
        std::fprintf(stderr, "usage: %s N NC REPS\n", argv[0]);
        return 2;
    }
    const int n = std::atoi(argv[1]);
    const int nc = std::atoi(argv[2]);
    const int reps = std::atoi(argv[3]);
    if (n <= 0 || n % QK_K != 0 || nc <= 0 || nc % 8 != 0 || reps < 3) {
        return 2;
    }

    inputs input = make_inputs(n, nc);
    std::vector<float> reference(nc, 0.0f);
    std::vector<float> output8(nc, 0.0f);
    std::vector<float> output4(nc, 0.0f);
    std::vector<float> output_decoded(nc, 0.0f);
    const block_q4_Kx8_decoded_view decoded_view{
        input.interleave4.data(), input.decoded.data(),
    };
    ggml_gemv_q4_K_8x8_q8_K_generic(
        n, reference.data(), nc, input.interleave8.data(), input.q8.data(), 1, nc);
    ggml_gemv_q4_K_8x8_q8_K(
        n, output8.data(), nc, input.interleave8.data(), input.q8.data(), 1, nc);
    ggml_gemv_q4_K_8x4_q8_K(
        n, output4.data(), nc, input.interleave4.data(), input.q8.data(), 1, nc);
    ggml_gemv_q4_K_8x4_q8_K_decoded(
        n, output_decoded.data(), nc, &decoded_view, input.q8.data(), 1, nc);
    const double nmse8 = nmse(reference, output8);
    const double nmse4 = nmse(reference, output4);
    const double nmse_decoded = nmse(reference, output_decoded);
    if (nmse8 > 5e-4 || nmse4 > 5e-4 || nmse_decoded > 5e-4) {
        std::fprintf(stderr, "correctness failed: nmse8=%.12g nmse4=%.12g nmse_decoded=%.12g\n",
                     nmse8, nmse4, nmse_decoded);
        return 1;
    }

    std::vector<double> samples8;
    std::vector<double> samples4;
    std::vector<double> samples_decoded;
    samples8.reserve(reps);
    samples4.reserve(reps);
    samples_decoded.reserve(reps);
    for (int rep = 0; rep < reps; ++rep) {
        if (rep % 3 == 0) {
            samples8.push_back(time_call(ggml_gemv_q4_K_8x8_q8_K, n, nc,
                                         input.interleave8.data(), input.q8.data(), output8));
            samples4.push_back(time_call(ggml_gemv_q4_K_8x4_q8_K, n, nc,
                                         input.interleave4.data(), input.q8.data(), output4));
            samples_decoded.push_back(time_call(ggml_gemv_q4_K_8x4_q8_K_decoded, n, nc,
                                                 &decoded_view, input.q8.data(), output_decoded));
        } else if (rep % 3 == 1) {
            samples4.push_back(time_call(ggml_gemv_q4_K_8x4_q8_K, n, nc,
                                         input.interleave4.data(), input.q8.data(), output4));
            samples_decoded.push_back(time_call(ggml_gemv_q4_K_8x4_q8_K_decoded, n, nc,
                                                 &decoded_view, input.q8.data(), output_decoded));
            samples8.push_back(time_call(ggml_gemv_q4_K_8x8_q8_K, n, nc,
                                         input.interleave8.data(), input.q8.data(), output8));
        } else {
            samples_decoded.push_back(time_call(ggml_gemv_q4_K_8x4_q8_K_decoded, n, nc,
                                                 &decoded_view, input.q8.data(), output_decoded));
            samples8.push_back(time_call(ggml_gemv_q4_K_8x8_q8_K, n, nc,
                                         input.interleave8.data(), input.q8.data(), output8));
            samples4.push_back(time_call(ggml_gemv_q4_K_8x4_q8_K, n, nc,
                                         input.interleave4.data(), input.q8.data(), output4));
        }
    }

    const double median8 = median(samples8);
    const double median4 = median(samples4);
    const double median_decoded = median(samples_decoded);
    double checksum = 0.0;
    for (float value : output4) {
        checksum += value;
    }
    std::printf(
        "n=%d nc=%d reps=%d nmse8=%.12g nmse4=%.12g nmse_decoded=%.12g "
        "interleave8_us=%.6f interleave4_us=%.6f decoded_us=%.6f "
        "interleave4_ratio=%.9f decoded_ratio=%.9f metadata_bytes=%zu checksum=%.12g\n",
        n, nc, reps, nmse8, nmse4, nmse_decoded, median8, median4, median_decoded,
        median8 / median4, median8 / median_decoded,
        input.decoded.size() * sizeof(block_q4_Kx8_decoded), checksum);
    return 0;
}
