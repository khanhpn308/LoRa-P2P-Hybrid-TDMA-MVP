#pragma once
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

static inline void mbedtls_platform_zeroize(void *buf, size_t len) {
    if (!buf || len == 0) return;
    volatile unsigned char *p = (volatile unsigned char *)buf;
    while (len--) {
        *p++ = 0;
    }
}

#ifdef __cplusplus
}
#endif
