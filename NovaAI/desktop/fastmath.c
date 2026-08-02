/*
 * nova_fastmath.dll — small Windows helpers for Nova's pure-Python engine.
 * Speeds up matrix-vector multiply and float16→float32 decode.
 */
#include <stdint.h>
#include <stddef.h>
#include <math.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

/* out[rows] = W[rows][cols] * x[cols]  (row-major W) */
EXPORT void nova_matvec(float *out, const float *W, const float *x,
                        int rows, int cols) {
    for (int i = 0; i < rows; i++) {
        const float *row = W + (long)i * (long)cols;
        double s = 0.0;
        int j = 0;
        /* 4-wide accum helps MSVC/GCC autovec a bit */
        for (; j + 3 < cols; j += 4) {
            s += (double)row[j] * (double)x[j]
               + (double)row[j + 1] * (double)x[j + 1]
               + (double)row[j + 2] * (double)x[j + 2]
               + (double)row[j + 3] * (double)x[j + 3];
        }
        for (; j < cols; j++)
            s += (double)row[j] * (double)x[j];
        out[i] = (float)s;
    }
}

/* out[rows] = W[rows][cols] * x[cols] + bias[rows] */
EXPORT void nova_matvec_bias(float *out, const float *W, const float *x,
                             const float *bias, int rows, int cols) {
    for (int i = 0; i < rows; i++) {
        const float *row = W + (long)i * (long)cols;
        double s = (double)bias[i];
        int j = 0;
        for (; j + 3 < cols; j += 4) {
            s += (double)row[j] * (double)x[j]
               + (double)row[j + 1] * (double)x[j + 1]
               + (double)row[j + 2] * (double)x[j + 2]
               + (double)row[j + 3] * (double)x[j + 3];
        }
        for (; j < cols; j++)
            s += (double)row[j] * (double)x[j];
        out[i] = (float)s;
    }
}

/* Decode little-endian IEEE half floats into float32. */
EXPORT void nova_f16_to_f32(float *out, const uint16_t *in, int n) {
    for (int i = 0; i < n; i++) {
        uint16_t h = in[i];
        uint32_t sign = (uint32_t)(h & 0x8000u) << 16;
        uint32_t exp = (h >> 10) & 0x1Fu;
        uint32_t mant = h & 0x3FFu;
        uint32_t f;
        if (exp == 0) {
            if (mant == 0) {
                f = sign;
            } else {
                /* subnormal → normalize */
                exp = 127 - 15 + 1;
                while ((mant & 0x400u) == 0) {
                    mant <<= 1;
                    exp--;
                }
                mant &= 0x3FFu;
                f = sign | (exp << 23) | (mant << 13);
            }
        } else if (exp == 31) {
            f = sign | 0x7F800000u | (mant << 13);
        } else {
            f = sign | ((exp + (127 - 15)) << 23) | (mant << 13);
        }
        out[i] = *(float *)&f;
    }
}

/* LayerNorm: out = (x - mean) / sqrt(var+eps) * w + b */
EXPORT void nova_layernorm(float *out, const float *x, const float *w,
                           const float *b, int n) {
    double mean = 0.0;
    for (int i = 0; i < n; i++)
        mean += (double)x[i];
    mean /= (double)n;
    double var = 0.0;
    for (int i = 0; i < n; i++) {
        double d = (double)x[i] - mean;
        var += d * d;
    }
    var /= (double)n;
    double inv = 1.0 / sqrt(var + 1e-5);
    for (int i = 0; i < n; i++)
        out[i] = (float)(((double)x[i] - mean) * inv * (double)w[i] + (double)b[i]);
}
