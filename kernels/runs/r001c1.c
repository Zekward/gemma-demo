#include <arm_neon.h>
#include <stdint.h>

#define QK 32
typedef _Float16 half;
typedef struct { half d; uint8_t qs[QK/2]; } block_q4_0;
typedef struct { half d; int8_t  qs[QK];   } block_q8_0;

void vec_dot_candidate(int n, float * restrict s, const void * restrict vx, const void * restrict vy) {
    const int nb = n / QK;
    const block_q4_0 * restrict x = (const block_q4_0 *)vx;
    const block_q8_0 * restrict y = (const block_q8_0 *)vy;

    float32x4_t acc0 = vdupq_n_f32(0.0f);
    float32x4_t acc1 = vdupq_n_f32(0.0f);
    float32x4_t acc2 = vdupq_n_f32(0.0f);
    float32x4_t acc3 = vdupq_n_f32(0.0f);

    const uint8x16_t m4 = vdupq_n_u8(0x0F);
    const int32x4_t v8 = vdupq_n_s32(8);

    int i = 0;
    for (; i <= nb - 4; i += 4) {
        // Prefetch data for future iterations
        __builtin_prefetch(&x[i + 8], 0, 3);
        __builtin_prefetch(&y[i + 8], 0, 3);

        // Unroll 4 blocks to saturate pipeline and hide latency
        for (int j = 0; j < 4; j++) {
            int idx = i + j;
            const uint8x16_t pk = vld1q_u8(x[idx].qs);
            const int8x16_t yl = vld1q_s8(y[idx].qs);
            const int8x16_t yh = vld1q_s8(y[idx].qs + 16);

            int8x16_t xl = vreinterpretq_s8_u8(vandq_u8(pk, m4));
            int8x16_t xh = vreinterpretq_s8_u8(vshrq_n_u8(pk, 4));

            // sum((x-8)*y) = sum(x*y) - 8*sum(y)
            int16x8_t p = vmull_s8(vget_low_s8(xl), vget_low_s8(yl));
            p = vmlal_s8(p, vget_high_s8(xl), vget_high_s8(yl));
            p = vmlal_s8(p, vget_low_s8(xh), vget_low_s8(yh));
            p = vmlal_s8(p, vget_high_s8(xh), vget_high_s8(yh));

            int32x4_t sum_xy = vpaddlq_s16(p);
            
            // Calculate sum(y) for the -8*sum(y) term
            int16x8_t sy = vpaddq_s8(yl, yh);
            int32x4_t sum_y = vpaddlq_s16(sy);
            
            // Final integer block sum: sum(x*y) - 8*sum(y)
            int32x4_t block_sum = vsubq_s32(sum_xy, vmulq_s32(v8, sum_y));
            
            float scale = (float)x[idx].d * (float)y[idx].d;
            
            // Distribute to different accumulators to break dep chains
            if (j == 0) acc0 = vmlaq_n_f32(acc0, vcvtq_f32_s32(block_sum), scale);
            else if (j == 1) acc1 = vmlaq_n_f32(acc1, vcvtq_f32_s32(block_sum), scale);
            else if (j == 2) acc2 = vmlaq_n_f32(acc2, vcvtq_f32_s32(block_sum), scale);
            else acc3 = vmlaq_n_f32(acc3, vcvtq_f32_s32(block_sum), scale);
        }
    }

    // Tail handling
    for (; i < nb; i++) {
        const uint8x16_t pk = vld1q_u8(x[i].qs);
        const int8x16_t yl = vld1q_s8(y[i].qs);
        const int8x16_t yh = vld1q_s8(y[i].qs + 16);
        int8x16_t xl = vreinterpretq_s8_u8(vandq_u8(pk, m4));
        int8x16_t xh = vreinterpretq_s8_u8(vshrq_n_u8(pk, 4));
        int16x8_t p = vmull_s8(vget_low_s8(xl), vget_low_s8(yl));
        p = vmlal_s8(p, vget_high_s8(xl), vget_high_s8(yl));
        p = vmlal_s8(p, vget_low_s8(xh), vget_low_s8(yh));
        p = vmlal_s8(p, vget_high_s8(xh), vget_high_s8(yh));
        int32x4_t sum_xy = vpaddlq_s16(p);
        int16x8_t sy = vpaddq_s8(yl, yh);
        int32x4_t sum_y = vpaddlq_s16(sy);
        int32x4_t block_sum = vsubq_s32(sum_xy, vmulq_s32(v8, sum_y));
        acc0 = vmlaq_n_f32(acc0, vcvtq_f32_s32(block_sum), (float)x[i].d * (float)y[i].d);
    }

    float final_s = vaddvq_f32(acc0) + vaddvq_f32(acc1) + vaddvq_f32(acc2) + vaddvq_f32(acc3);
    *s = final_s;
}