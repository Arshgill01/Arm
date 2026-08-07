#include <arm_neon.h>

#include <cstdint>
#include <cstdio>

static void print_result(const char * name, int8x16_t rhs) {
    uint8_t lhs_values[16];
    for (int index = 0; index < 8; ++index) {
        lhs_values[index] = static_cast<uint8_t>(index + 1);
        lhs_values[index + 8] = static_cast<uint8_t>(index + 11);
    }
    const uint8x16_t lhs = vld1q_u8(lhs_values);
    const int32x4_t result = vusmmlaq_s32(vdupq_n_s32(0), lhs, rhs);
    int32_t lanes[4];
    vst1q_s32(lanes, result);
    std::printf("%s=%d,%d,%d,%d\n", name, lanes[0], lanes[1], lanes[2], lanes[3]);
}

int main() {
    int8_t contiguous_values[16];
    int8_t interleaved_values[16];
    for (int index = 0; index < 8; ++index) {
        contiguous_values[index] = static_cast<int8_t>(index + 1);
        contiguous_values[index + 8] = static_cast<int8_t>(index + 1);
        interleaved_values[2 * index] = static_cast<int8_t>(index + 1);
        interleaved_values[2 * index + 1] = static_cast<int8_t>(index + 1);
    }
    print_result("contiguous", vld1q_s8(contiguous_values));
    print_result("interleaved", vld1q_s8(interleaved_values));
    return 0;
}
