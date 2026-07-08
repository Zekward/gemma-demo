#include <arm_neon.h>
#include <stdint.h>

#define QK 32
typedef _Float16 half;
typedef struct { half d; uint8_t qs[16]; } block_q4_0;
typedef struct { half d; int8_t  qs[32]; } block_q8_0;

void vec_dot_candidate(int n, float * restrict s, const void * restrict vx, const void * restrict vy) {
    const int nb = n / QK;
    const block_q4_0 * restrict x = (const block_q4_0 *)vx;
    const block_q8_0 * restrict y = (const block_q8_0 *)vy;

    float32x4_t acc0 = vdupq_n_f32(0.0f);
    float32x4_t acc1 = vdupq_n_f32(0.0f);
    float32x4_t acc2 = vdupq_n_f32(0.0f);
    float32x4_t acc3 = vdupq_n_f32(0.0f);

    const uint8x16_t mask = vdupq_n_u8(0x0F);
    int i = 0;

    // Unroll by 4 to break dependency chains and hide load latency
    for (; i <= nb - 4; i += 4) {
        // Prefetch next blocks
        __builtin_prefetch(&x[i + 8]);
        __builtin_prefetch(&y[i + 8]);

        for (int j = 0; j < 4; j++) {
            const block_q4_0 *bx = &x[i + j];
            const block_q8_0 *by = &y[i + j];

            uint8x16_t pk = vld1q_u8(bx->qs);
            int8x16_t xl = vreinterpretq_s8_u8(vandq_u8(pk, mask));
            int8x16_t xh = vreinterpretq_s8_u8(vshrq_n_u8(pk, 4));

            int8x16_t yl = vld1q_s8(by->qs);
            int8x16_t yh = vld1q_s8(by->qs + 16);

            // sum((x-8)*y) = sum(x*y) - 8*sum(y)
            int16x8_t p = vmull_s8(vget_low_s8(xl), vget_low_s8(yl));
            p = vmlal_s8(p, vget_high_s8(xl), vget_high_s8(yl));
            p = vmlal_s8(p, vget_low_s8(xh), vget_low_s8(yh));
            p = vmlal_s8(p, vget_high_s8(xh), vget_high_s8(yh));

            // Compute sum(y) for the bias term
            int16x8_t sy = vpaddlq_s8(yl);
            int16x8_t syh = vpaddlq_s8(yh);
            int32x4_t sum_y = vpaddlq_s16(vaddq_s16(sy, syh));

            int32x4_t sum_xy = vpaddlq_s16(p);
            // block_sum = sum_xy - 8 * sum_y
            int32x4_t block_sum = vsubq_s32(sum_xy, vshlq_n_s32(sum_y, 3));

            float d = (float)bx->d * (float)by->d;
            float32x4_t val = vmlaq_n_f32(vcvtq_f32_s32(block_sum), d, 0.0f);
            
            if (j == 0) acc0 = vaddq_f32(acc0, val);
            else if (j == 1) acc1 = vaddq_f32(acc1, val);
            else if (j == 2) acc2 = vaddq_f32(acc2, val);
            else acc3 = vaddq_f32(acc3, val);
        }
    }

    // Tail
    for (; i < nb; i++) {
        uint8x16_t pk = vld1q_u8(x[i].qs);
        int8x16_t xl = vreinterpretq_s8_u8(vandq_u8(pk, mask));
        int8x16_t xh = vreinterpretq_s8_u8(vshrq_n_u8(pk, 4));
        int8x16_t yl = vld1q_s8(y[i].qs);
        int8x16_t yh = vld1q_s8(y[i].qs + 16);

        int16x8_t p = vmull_s8(vget_low_s8(xl), vget_low_s8(yl));
        p = vmlal_s8(p, vget_high_s8(xl), vget_high_s8(yl));
        p = vmlal_s8(p, vget_low_s8(xh), vget_low_s8(yh));
        p = vmlal_s8(p, vget_high_s8(xh), vget_high_s8(yh));

        int16x8_t sy = vpaddlq_s8(yl);
        int16x8_t syh = vpaddlq_s8(yh);
        int32x4_t sum_y = vpaddlq_s16(vaddq_s16(sy, syh));
        int32x4_t block_sum = vsubq_s32(vpaddlq_s16(p), vshlq_n_s32(sum_y, 3));

        float d = (float)x[i].d * (float)y[i].d;
        acc0 = vmlaq_n_f32(acc0, vcvtq_f32_s32(block_sum), d);
    }

    float final_sum = vaddvq_f32(acc0) + vaddvq_f32(acc1) + vaddvq_f32(acc2) + vaddvq_f32(acc3);
    *s = final_sum;
}