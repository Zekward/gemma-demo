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
    
    const uint8x16_t m4 = vdupq_n_u8(0x0F);
    const int8x16_t  k8 = vdupq_n_s8(8);

    int i = 0;
    // Unroll by 2 to break dependency chains and improve pipeline utilization
    for (; i <= nb - 2; i += 2) {
        const block_q4_0 *bx = &x[i];
        const block_q8_0 *by = &y[i];
        __builtin_prefetch(&x[i + 4], 0, 3);
        __builtin_prefetch(&y[i + 4], 0, 3);

        // Block i
        uint8x16_t pk0 = vld1q_u8(bx[0].qs);
        int8x16_t xl0 = vreinterpretq_s8_u8(vandq_u8(pk0, m4));
        int8x16_t xh0 = vreinterpretq_s8_u8(vshrq_n_u8(pk0, 4));
        int8x16_t yl0 = vld1q_s8(by[0].qs);
        int8x16_t yh0 = vld1q_s8(by[0].qs + 16);

        int16x8_t p0 = vmull_s8(vget_low_s8(xl0), vget_low_s8(yl0));
        p0 = vmlal_s8(p0, vget_high_s8(xl0), vget_high_s8(yl0));
        p0 = vmlal_s8(p0, vget_low_s8(xh0), vget_low_s8(yh0));
        p0 = vmlal_s8(p0, vget_high_s8(xh0), vget_high_s8(yh0));

        // Block i+1
        uint8x16_t pk1 = vld1q_u8(bx[1].qs);
        int8x16_t xl1 = vreinterpretq_s8_u8(vandq_u8(pk1, m4));
        int8x16_t xh1 = vreinterpretq_s8_u8(vshrq_n_u8(pk1, 4));
        int8x16_t yl1 = vld1q_s8(by[1].qs);
        int8x16_t yh1 = vld1q_s8(by[1].qs + 16);

        int16x8_t p1 = vmull_s8(vget_low_s8(xl1), vget_low_s8(yl1));
        p1 = vmlal_s8(p1, vget_high_s8(xl1), vget_high_s8(yl1));
        p1 = vmlal_s8(p1, vget_low_s8(xh1), vget_low_s8(yh1));
        p1 = vmlal_s8(p1, vget_high_s8(xh1), vget_high_s8(yh1));

        // Apply bias: sum((x-8)*y) = sum(x*y) - 8*sum(y)
        // We subtract 8 * sum(y_block) from the integer sum
        int32x4_t sumi0 = vpaddlq_s16(p0);
        int32x4_t sumi1 = vpaddlq_s16(p1);
        
        // sum(y_block) = sum(yl) + sum(yh)
        int16x8_t ysum0 = vpaddq_s8(yl0, yh0);
        int32x4_t ysum0_32 = vpaddlq_s16(ysum0);
        sumi0 = vmlaq_n_s32(sumi0, ysum0_32, -8);

        int16x8_t ysum1 = vpaddq_s8(yl1, yh1);
        int32x4_t ysum1_32 = vpaddlq_s16(ysum1);
        sumi1 = vmlaq_n_s32(sumi1, ysum1_32, -8);

        float d0 = (float)bx[0].d * (float)by[0].d;
        float d1 = (float)bx[1].d * (float)by[1].d;
        
        acc0 = vmlaq_n_f32(acc0, vcvtq_f32_s32(sumi0), d0);
        acc1 = vmlaq_n_f32(acc1, vcvtq_f32_s32(sumi1), d1);
    }

    // Tail
    for (; i < nb; i++) {
        uint8x16_t pk = vld1q_u8(x[i].qs);
        int8x16_t xl = vreinterpretq_s8_u8(vandq_u8(pk, m4));
        int8x16_t xh = vreinterpretq_s8_u8(vshrq_n_u8(pk, 4));
        int8x16_t yl = vld1q_s8(y[i].qs);
        int8x16_t yh = vld1q_s8(y[i].qs + 16);

        int16x8_t p = vmull_s8(vget_low_s8(xl), vget_low_s8(yl));
        p = vmlal_s8(p, vget_high_s8(xl), vget_high_s8(yl));
        p = vmlal_s8(p, vget_low_s8(xh), vget_low_s8(yh));
        p = vmlal_s8(p, vget_high_s8(xh), vget_high_s8(yh));

        int32x4_t sumi = vpaddlq_s16(p);
        int16x8_t ysum = vpaddq_s8(yl, yh);
        sumi = vmlaq_n_s32(sumi, vpaddlq_s16(ysum), -8);

        float d = (float)x[i].d * (float)y[i].d;
        acc0 = vmlaq_n_f32(acc0, vcvtq_f32_s32(sumi), d);
    }

    *s = vaddvq_f32(vaddq_f32(acc0, acc1));
}