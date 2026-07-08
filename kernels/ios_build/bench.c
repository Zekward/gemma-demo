// bench.c — FIXED benchmark harness for the Q4_0 x Q8_0 vec_dot autoresearch loop.
//
// This file is TRUSTED and never rewritten by the model. Only candidate.c changes.
// It defines the canonical block formats (matching llama.cpp's ggml q4_0 / q8_0),
// a scalar REFERENCE dot used to check correctness, then #includes the candidate
// kernel and benchmarks it. Emits ONE JSON line on stdout that the driver parses.
//
// The dominant op in autoregressive decode is a quantized matrix-vector multiply:
// for each output row, dot(weight_row_q4_0, activation_q8_0). We simulate a
// [ROWS x D_IN] projection (activation reused across rows) — the real A9 bottleneck.
//
// Build (target the iPhone 6s ISA, run on host):
//   clang -O3 -arch arm64 -mcpu=apple-a9 bench.c -o bench
//
// Env knobs: D_IN (default 2048), ROWS (4096), SEED (1234), MIN_SECS (0.30).

#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
#include <time.h>

#define QK 32
typedef _Float16 half;                                   // fp16 storage; A9 has fp16<->fp32 convert
typedef struct { half d; uint8_t qs[QK/2]; } block_q4_0; // 18 bytes
typedef struct { half d; int8_t  qs[QK];   } block_q8_0; // 34 bytes

// ---- REFERENCE (trusted, scalar). Defines the exact semantics every candidate must match. ----
// q4_0 nibble layout (ggml): low nibbles pair with y[0..15], high nibbles with y[16..31];
// each quant value is (nibble - 8). Per block: sumi = Σ (xq-8)*yq, then accumulate d_x*d_y*sumi.
static void vec_dot_ref(int n, float *s, const void *vx, const void *vy) {
    const int nb = n / QK;
    const block_q4_0 *x = (const block_q4_0 *)vx;
    const block_q8_0 *y = (const block_q8_0 *)vy;
    float sumf = 0.0f;
    for (int i = 0; i < nb; i++) {
        int sumi = 0;
        for (int j = 0; j < QK/2; j++) {
            const int x0 = (x[i].qs[j] & 0x0F) - 8;
            const int x1 = (x[i].qs[j] >>   4) - 8;
            sumi += x0 * (int)y[i].qs[j];
            sumi += x1 * (int)y[i].qs[j + QK/2];
        }
        sumf += (float)x[i].d * (float)y[i].d * (float)sumi;
    }
    *s = sumf;
}

// ---- CANDIDATE (rewritten every iteration by gemma-4-31b on Cerebras) ----
// Compiled as a SEPARATE translation unit (like llama.cpp's out-of-line vec_dot,
// called via function pointer — never inlined into the matvec). Self-contained;
// defines its own identical block types. Build: clang ... bench.c candidate.c -o bench
void vec_dot_candidate(int n, float *s, const void *vx, const void *vy);

// ------------------------------------------------------------------------------------
static inline double now_s(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
}
static uint64_t rng_state = 88172645463325252ull;
static inline uint64_t xorshift(void) {
    rng_state ^= rng_state << 13; rng_state ^= rng_state >> 7; rng_state ^= rng_state << 17;
    return rng_state;
}

int main(void) {
    const int D_IN = getenv("D_IN") ? atoi(getenv("D_IN")) : 2048;
    const int ROWS = getenv("ROWS") ? atoi(getenv("ROWS")) : 4096;
    const double MIN_SECS = getenv("MIN_SECS") ? atof(getenv("MIN_SECS")) : 0.30;
    if (getenv("SEED")) rng_state = (uint64_t)strtoull(getenv("SEED"), 0, 10) | 1;
    if (D_IN % QK != 0) { printf("{\"ok\":false,\"error\":\"D_IN must be multiple of 32\"}\n"); return 1; }
    const int nb = D_IN / QK;

    // x = ROWS weight rows (q4_0); y = one activation vector (q8_0), reused across rows.
    // posix_memalign: 64B-aligned base, portable across host macOS and iOS (all versions).
    block_q4_0 *x = NULL; block_q8_0 *y = NULL;
    if (posix_memalign((void **)&x, 64, (size_t)ROWS * nb * sizeof(block_q4_0)) ||
        posix_memalign((void **)&y, 64, (size_t)nb * sizeof(block_q8_0)) || !x || !y) {
        printf("{\"ok\":false,\"error\":\"alloc failed\"}\n"); return 1;
    }
    for (size_t i = 0; i < (size_t)ROWS * nb; i++) {
        x[i].d = (half)(0.015f + (xorshift() % 200) * 0.001f);
        for (int j = 0; j < QK/2; j++) x[i].qs[j] = (uint8_t)(xorshift() & 0xFF);
    }
    for (int i = 0; i < nb; i++) {
        y[i].d = (half)(0.015f + (xorshift() % 200) * 0.001f);
        for (int j = 0; j < QK; j++) y[i].qs[j] = (int8_t)(xorshift() & 0xFF);
    }

    // ---- correctness: candidate vs reference over a sample of rows ----
    double max_abs = 0.0, max_rel = 0.0;
    const int CHK = ROWS < 256 ? ROWS : 256;
    for (int r = 0; r < CHK; r++) {
        float ref, cand;
        vec_dot_ref(D_IN, &ref, x + (size_t)r * nb, y);
        vec_dot_candidate(D_IN, &cand, x + (size_t)r * nb, y);
        const double a = fabs((double)cand - (double)ref);
        const double rel = a / (fabs((double)ref) + 1e-6);
        if (a > max_abs) max_abs = a;
        if (rel > max_rel) max_rel = rel;
    }
    const int ok = (max_rel <= 1e-3) || (max_abs <= 1e-2);

    // ---- timing: adaptive — repeat full matvec passes until >= MIN_SECS ----
    volatile float sink = 0.0f;
    { float t; for (int r = 0; r < ROWS; r++) { vec_dot_candidate(D_IN, &t, x + (size_t)r*nb, y); sink += t; } } // warm
    long passes = 0; double elapsed = 0.0; const double t0 = now_s();
    do {
        float t;
        for (int r = 0; r < ROWS; r++) { vec_dot_candidate(D_IN, &t, x + (size_t)r*nb, y); sink += t; }
        passes++; elapsed = now_s() - t0;
    } while (elapsed < MIN_SECS);

    const double dots = (double)passes * ROWS;
    const double ns_per_dot = elapsed * 1e9 / dots;
    const double bytes_per_dot = (double)nb * (sizeof(block_q4_0) + 0); // weight bytes streamed (y stays hot)
    const double gbps   = bytes_per_dot / ns_per_dot;                   // GB/s of weight read
    const double gflops = (2.0 * D_IN) / ns_per_dot;                    // mul+add per element

    // "KBENCH_JSON " prefix lets device_bench.py scrape this line from the iOS console; the host
    // parser tolerates the prefix too.
    printf("KBENCH_JSON {\"ok\":%s,\"max_abs_err\":%.3e,\"max_rel_err\":%.3e,"
           "\"ns_per_dot\":%.3f,\"gflops\":%.2f,\"gbps\":%.2f,"
           "\"d_in\":%d,\"rows\":%d,\"passes\":%ld,\"checksum\":%.6f}\n",
           ok ? "true" : "false", max_abs, max_rel, ns_per_dot, gflops, gbps,
           D_IN, ROWS, passes, (double)sink);
    free(x); free(y);
    return ok ? 0 : 2;
}
