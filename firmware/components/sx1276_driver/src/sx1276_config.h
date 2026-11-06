#pragma once

#include "sx1276_types.h"
#include "sx1276_regs.h"

#ifdef __cplusplus
extern "C" {
#endif

esp_err_t sx1276_channel_to_frequency(uint8_t channel_idx, uint32_t *out_freq_hz);
esp_err_t sx1276_frequency_to_frf(uint32_t freq_hz, uint8_t *out_msb, uint8_t *out_mid, uint8_t *out_lsb);

#ifdef __cplusplus
}
#endif
