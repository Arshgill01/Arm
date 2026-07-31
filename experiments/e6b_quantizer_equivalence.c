// SPDX-License-Identifier: Apache-2.0

#include <arm_neon.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

enum { BLOCK_SIZE = 32, BLOCK_COUNT = 257, VALUE_COUNT = BLOCK_SIZE * BLOCK_COUNT };

typedef struct {
    __fp16 d;
    int8_t values[BLOCK_SIZE];
} block_q8_0;

_Static_assert(sizeof(block_q8_0) == 34, "unexpected Q8_0 block layout");

static __attribute__((noinline)) void quantize_baseline(
    const float * restrict input, block_q8_0 * restrict output)
{
    for (int block = 0; block < BLOCK_COUNT; ++block) {
        float32x4_t source[8];
        float32x4_t absolute[8];
        float32x4_t maximum[8];

        for (int lane = 0; lane < 8; ++lane) {
            source[lane] = vld1q_f32(input + block * BLOCK_SIZE + 4 * lane);
            absolute[lane] = vabsq_f32(source[lane]);
        }
        for (int lane = 0; lane < 4; ++lane) {
            maximum[2 * lane] = vmaxq_f32(absolute[2 * lane], absolute[2 * lane + 1]);
        }
        for (int lane = 0; lane < 2; ++lane) {
            maximum[4 * lane] = vmaxq_f32(maximum[4 * lane], maximum[4 * lane + 2]);
        }
        maximum[0] = vmaxq_f32(maximum[0], maximum[4]);

        const float scale = vmaxvq_f32(maximum[0]) / 127.0f;
        const float inverse = scale ? 1.0f / scale : 0.0f;
        output[block].d = (__fp16) scale;
        for (int lane = 0; lane < 8; ++lane) {
            const int32x4_t quantized =
                vcvtnq_s32_f32(vmulq_n_f32(source[lane], inverse));
            output[block].values[4 * lane + 0] = vgetq_lane_s32(quantized, 0);
            output[block].values[4 * lane + 1] = vgetq_lane_s32(quantized, 1);
            output[block].values[4 * lane + 2] = vgetq_lane_s32(quantized, 2);
            output[block].values[4 * lane + 3] = vgetq_lane_s32(quantized, 3);
        }
    }
}

static __attribute__((noinline)) void quantize_patched(
    const float * restrict input, block_q8_0 * restrict output)
{
    for (int block = 0; block < BLOCK_COUNT; ++block) {
        float32x4_t source[8];
        float32x4_t absolute[8];
        float32x4_t maximum[8];

        for (int lane = 0; lane < 8; ++lane) {
            source[lane] = vld1q_f32(input + block * BLOCK_SIZE + 4 * lane);
            absolute[lane] = vabsq_f32(source[lane]);
        }
        for (int lane = 0; lane < 4; ++lane) {
            maximum[2 * lane] = vmaxq_f32(absolute[2 * lane], absolute[2 * lane + 1]);
        }
        for (int lane = 0; lane < 2; ++lane) {
            maximum[4 * lane] = vmaxq_f32(maximum[4 * lane], maximum[4 * lane + 2]);
        }
        maximum[0] = vmaxq_f32(maximum[0], maximum[4]);

        const float scale = vmaxvq_f32(maximum[0]) / 127.0f;
        const float inverse = scale ? 1.0f / scale : 0.0f;
        output[block].d = (__fp16) scale;

        int32x4_t quantized[8];
        for (int lane = 0; lane < 8; ++lane) {
            quantized[lane] = vcvtnq_s32_f32(vmulq_n_f32(source[lane], inverse));
        }
        const int16x8_t q0 = vcombine_s16(vmovn_s32(quantized[0]), vmovn_s32(quantized[1]));
        const int16x8_t q1 = vcombine_s16(vmovn_s32(quantized[2]), vmovn_s32(quantized[3]));
        const int16x8_t q2 = vcombine_s16(vmovn_s32(quantized[4]), vmovn_s32(quantized[5]));
        const int16x8_t q3 = vcombine_s16(vmovn_s32(quantized[6]), vmovn_s32(quantized[7]));

        vst1q_s8(output[block].values,
                 vcombine_s8(vmovn_s16(q0), vmovn_s16(q1)));
        vst1q_s8(output[block].values + 16,
                 vcombine_s8(vmovn_s16(q2), vmovn_s16(q3)));
    }
}

int main(void)
{
    float input[VALUE_COUNT];
    block_q8_0 baseline[BLOCK_COUNT];
    block_q8_0 patched[BLOCK_COUNT];
    uint32_t state = 0x12345678U;

    for (int index = 0; index < VALUE_COUNT; ++index) {
        state = state * 1664525U + 1013904223U;
        input[index] =
            ((int32_t) (state >> 8) / 8388608.0f) * (1.0f + index % 17);
    }
    memset(input + BLOCK_SIZE * 128, 0, BLOCK_SIZE * sizeof(float));

    quantize_baseline(input, baseline);
    quantize_patched(input, patched);
    if (memcmp(baseline, patched, sizeof(baseline)) != 0) {
        fputs("E6b quantizer outputs differ\n", stderr);
        return 1;
    }
    printf("bit-identical finite_values=%d zero_block=true\n", VALUE_COUNT);
    return 0;
}
