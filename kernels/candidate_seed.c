// candidate_seed.c — the starting champion: a correct, plain NEON Q4_0 x Q8_0 dot
// for ARMv8-A *baseline* (Apple A9 / iPhone 6s). NO dotprod (sdot/udot) and NO i8mm —
// the A9 predates those. Improvements must come from scheduling, unrolling, fewer
// converts, prefetch, and better dual-issue — not newer instructions.
//
// Required ABI (do not change): n is a multiple of 32; vx -> block_q4_0[n/32];
// vy -> block_q8_0[n/32]; write the scalar dot product to *s.
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

    float32x4_t acc = vdupq_n_f32(0.0f);
    const uint8x16_t m4 = vdupq_n_u8(0x0F);
    const int8x16_t  k8 = vdupq_n_s8(8);

    for (int i = 0; i < nb; i++) {
        const uint8x16_t pk = vld1q_u8(x[i].qs);                 // 16 packed bytes -> 32 nibbles
        int8x16_t xl = vreinterpretq_s8_u8(vandq_u8(pk, m4));    // low  nibbles -> y[0..15]
        int8x16_t xh = vreinterpretq_s8_u8(vshrq_n_u8(pk, 4));   // high nibbles -> y[16..31]
        xl = vsubq_s8(xl, k8);
        xh = vsubq_s8(xh, k8);

        const int8x16_t yl = vld1q_s8(y[i].qs);
        const int8x16_t yh = vld1q_s8(y[i].qs + 16);

        // widening multiply-accumulate (A9 has no dot-product instruction)
        int16x8_t p = vmull_s8(vget_low_s8(xl),  vget_low_s8(yl));
        p = vmlal_s8(p, vget_high_s8(xl), vget_high_s8(yl));
        p = vmlal_s8(p, vget_low_s8(xh),  vget_low_s8(yh));
        p = vmlal_s8(p, vget_high_s8(xh), vget_high_s8(yh));

        const int32x4_t sumi = vpaddlq_s16(p);                   // 8x i16 -> 4x i32
        const float d = (float)x[i].d * (float)y[i].d;           // per-block scale in fp32
        acc = vmlaq_n_f32(acc, vcvtq_f32_s32(sumi), d);
    }
    *s = vaddvq_f32(acc);
}
