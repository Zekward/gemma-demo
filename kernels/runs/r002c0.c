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

    float32x4_t acc_f = vdupq_n_f32(0.0f);
    const uint8x16_t mask = vdupq_n_u8(0x0F);
    
    int i = 0;
    // Unroll by 2 to hide latency and utilize dual-issue
    for (; i <= nb - 2; i += 2) {
        __builtin_prefetch(&x[i + 4]);
        __builtin_prefetch(&y[i + 4]);

        // Block i
        uint8x16_t pk0 = vld1q_u8(x[i].qs);
        int8x16_t xl0 = vreinterpretq_s8_u8(vandq_u8(pk0, mask));
        int8x16_t xh0 = vreinterpretq_s8_u8(vshrq_n_u8(pk0, 4));
        int8x16_t yl0 = vld1q_s8(y[i].qs);
        int8x16_t yh0 = vld1q_s8(y[i].qs + 16);

        // Block i+1
        uint8x16_t pk1 = vld1q_u8(x[i+1].qs);
        int8x16_t xl1 = vreinterpretq_s8_u8(vandq_u8(pk1, mask));
        int8x16_t xh1 = vreinterpretq_s8_u8(vshrq_n_u8(pk1, 4));
        int8x16_t yl1 = vld1q_s8(y[i+1].qs);
        int8x16_t yh1 = vld1q_s8(y[i+1].qs + 16);

        // Dot products for block i
        int16x8_t p0 = vmull_s8(vget_low_s8(xl0), vget_low_s8(yl0));
        p0 = vmlal_s8(p0, vget_high_s8(xl0), vget_high_s8(yl0));
        p0 = vmlal_s8(p0, vget_low_s8(xh0), vget_low_s8(yh0));
        p0 = vmlal_s8(p0, vget_high_s8(xh0), vget_high_s8(yh0));
        
        // Dot products for block i+1
        int16x8_t p1 = vmull_s8(vget_low_s8(xl1), vget_low_s8(yl1));
        p1 = vmlal_s8(p1, vget_high_s8(xl1), vget_high_s8(yl1));
        p1 = vmlal_s8(p1, vget_low_s8(xh1), vget_low_s8(yh1));
        p1 = vmlal_s8(p1, vget_high_s8(xh1), vget_high_s8(yh1));

        // sum((x-8)*y) = sum(x*y) - 8 * sum(y)
        // Calculate sum(y) for block i
        int16x8_t sy0 = vpaddlq_s8(yl0); 
        sy0 = vpaddlq_s16(vpaddlq_s8(yh0)); // This is a bit messy, let's use a simpler sum
        
        // Correct sum(y) for block i:
        int32_t sum_y0 = 0;
        int8x16_t y_all0_l = vld1q_s8(y[i].qs);
        int8x16_t y_all0_h = vld1q_s8(y[i].qs + 16);
        int16x8_t sy0_l = vpaddlq_s8(y_all0_l);
        int16x8_t sy0_h = vpaddlq_s8(y_all0_h);
        int32x4_t sy0_f = vpaddlq_s16(vaddq_s16(sy0_l, sy0_h));
        
        int16x8_t sy1_l = vpaddlq_s8(yl1);
        int16x8_t sy1_h = vpaddlq_s8(yh1);
        int32x4_t sy1_f = vpaddlq_s16(vaddq_s16(sy1_l, sy1_h));

        int32x4_t sumi0 = vpaddlq_s16(p0);
        int32x4_t sumi1 = vpaddlq_s16(p1);

        // block_sum = sum(x*y) - 8 * sum(y)
        sumi0 = vsubq_s32(sumi0, vshlq_n_s32(sy0_f, 3));
        sumi1 = vsubq_s32(sumi1, vshlq_n_s32(sy1_f, 3));

        float d0 = (float)x[i].d * (float)y[i].d;
        float d1 = (float)x[i+1].d * (float)y[i+1].d;

        acc_f = vmlaq_n_f32(acc_f, vcvtq_f32_s32(sumi0), d0);
        acc_f = vmlaq_n_f32(acc_f, vcvtq_f32_s32(sumi1), d1);
    }

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

        int16x8_t sy_l = vpaddlq_s8(yl);
        int16x8_t sy_h = vpaddlq_s8(yh);
        int32x4_t sy = vpaddlq_s16(vaddq_s16(sy_l, sy_h));

        int32x4_t sumi = vpaddlq_s16(p);
        sumi = vsubq_s32(sumi, vshlq_n_s32(sy, 3));

        float d = (float)x[i].d * (float)y[i].d;
        acc_f = vmlaq_n_f32(acc_f, vcvtq_f32_s32(sumi), d);
    }

    *s = vaddvq_f32(acc_f);
}