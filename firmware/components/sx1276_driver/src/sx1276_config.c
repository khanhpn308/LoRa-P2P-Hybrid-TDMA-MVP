#include "sx1276_config.h"
#include "sx1276_driver.h"
#include <math.h>
#include <string.h>

static const uint32_t s_vn920_channels[SX1276_VN920_CHANNEL_COUNT] = {
    920250000U, // CH00: 920.250 MHz
    920500000U, // CH01: 920.500 MHz
    920750000U, // CH02: 920.750 MHz
    921000000U, // CH03: 921.000 MHz
    921250000U, // CH04: 921.250 MHz
    921500000U, // CH05: 921.500 MHz
    921750000U, // CH06: 921.750 MHz
    922000000U, // CH07: 922.000 MHz
    922250000U, // CH08: 922.250 MHz
    922500000U, // CH09: 922.500 MHz
    922750000U  // CH10: 922.750 MHz
};

esp_err_t sx1276_channel_to_frequency(uint8_t channel_idx, uint32_t *out_freq_hz)
{
    if (channel_idx >= SX1276_VN920_CHANNEL_COUNT || out_freq_hz == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    *out_freq_hz = s_vn920_channels[channel_idx];
    return ESP_OK;
}

esp_err_t sx1276_frequency_to_frf(uint32_t freq_hz, uint8_t *out_msb, uint8_t *out_mid, uint8_t *out_lsb)
{
    if (out_msb == NULL || out_mid == NULL || out_lsb == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    // Carrier synthesizer step for 32 MHz oscillator:
    // Frf = round(freq_hz * 2^19 / 32,000,000)
    uint64_t frf64 = ((uint64_t)freq_hz << 19) + 16000000ULL;
    uint32_t frf = (uint32_t)(frf64 / 32000000ULL);

    *out_msb = (uint8_t)((frf >> 16) & 0xFFU);
    *out_mid = (uint8_t)((frf >> 8) & 0xFFU);
    *out_lsb = (uint8_t)(frf & 0xFFU);
    return ESP_OK;
}

esp_err_t sx1276_get_default_hw_config(sx1276_hw_config_t *out_hw)
{
    if (out_hw == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    out_hw->pin_sck            = (gpio_num_t)CONFIG_SX1276_PIN_SCK;
    out_hw->pin_miso           = (gpio_num_t)CONFIG_SX1276_PIN_MISO;
    out_hw->pin_mosi           = (gpio_num_t)CONFIG_SX1276_PIN_MOSI;
    out_hw->pin_cs             = (gpio_num_t)CONFIG_SX1276_PIN_CS;
    out_hw->pin_rst            = (gpio_num_t)CONFIG_SX1276_PIN_RST;
    out_hw->pin_dio0           = (gpio_num_t)CONFIG_SX1276_PIN_DIO0;
    out_hw->spi_host           = SPI2_HOST;
    out_hw->spi_clock_speed_hz = CONFIG_SX1276_SPI_CLOCK_MHZ * 1000000;
    return ESP_OK;
}

esp_err_t sx1276_get_default_phy_config(sx1276_phy_config_t *out_phy)
{
    if (out_phy == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    memset(out_phy, 0, sizeof(sx1276_phy_config_t));

#if defined(CONFIG_SX1276_CHANNEL_CH01)
    out_phy->channel_idx = 1;
#elif defined(CONFIG_SX1276_CHANNEL_CH02)
    out_phy->channel_idx = 2;
#elif defined(CONFIG_SX1276_CHANNEL_CH03)
    out_phy->channel_idx = 3;
#elif defined(CONFIG_SX1276_CHANNEL_CH04)
    out_phy->channel_idx = 4;
#elif defined(CONFIG_SX1276_CHANNEL_CH05)
    out_phy->channel_idx = 5;
#elif defined(CONFIG_SX1276_CHANNEL_CH06)
    out_phy->channel_idx = 6;
#elif defined(CONFIG_SX1276_CHANNEL_CH07)
    out_phy->channel_idx = 7;
#elif defined(CONFIG_SX1276_CHANNEL_CH08)
    out_phy->channel_idx = 8;
#elif defined(CONFIG_SX1276_CHANNEL_CH09)
    out_phy->channel_idx = 9;
#elif defined(CONFIG_SX1276_CHANNEL_CH10)
    out_phy->channel_idx = 10;
#else
    out_phy->channel_idx = 0; // Default CH00
#endif

    sx1276_channel_to_frequency(out_phy->channel_idx, &out_phy->frequency_hz);

#if defined(CONFIG_SX1276_SF_8)
    out_phy->sf = SX1276_SF_8;
#elif defined(CONFIG_SX1276_SF_9)
    out_phy->sf = SX1276_SF_9;
#elif defined(CONFIG_SX1276_SF_10)
    out_phy->sf = SX1276_SF_10;
#elif defined(CONFIG_SX1276_SF_11)
    out_phy->sf = SX1276_SF_11;
#elif defined(CONFIG_SX1276_SF_12)
    out_phy->sf = SX1276_SF_12;
#else
    out_phy->sf = SX1276_SF_7;
#endif

#if defined(CONFIG_SX1276_BW_250K)
    out_phy->bw = SX1276_BW_250K;
#elif defined(CONFIG_SX1276_BW_500K)
    out_phy->bw = SX1276_BW_500K;
#else
    out_phy->bw = SX1276_BW_125K;
#endif

#if defined(CONFIG_SX1276_CR_4_6)
    out_phy->cr = SX1276_CR_4_6;
#elif defined(CONFIG_SX1276_CR_4_7)
    out_phy->cr = SX1276_CR_4_7;
#elif defined(CONFIG_SX1276_CR_4_8)
    out_phy->cr = SX1276_CR_4_8;
#else
    out_phy->cr = SX1276_CR_4_5;
#endif

    out_phy->preamble_len          = CONFIG_SX1276_PREAMBLE_LENGTH;
    out_phy->sync_word             = (uint8_t)CONFIG_SX1276_SYNC_WORD;

#if defined(CONFIG_SX1276_PAYLOAD_CRC_ON)
    out_phy->payload_crc_on        = true;
#else
    out_phy->payload_crc_on        = false;
#endif

#if defined(CONFIG_SX1276_EXPLICIT_HEADER)
    out_phy->explicit_header       = true;
#else
    out_phy->explicit_header       = false;
#endif

#if defined(CONFIG_SX1276_LDRO_FORCE_ON)
    out_phy->ldro_mode             = SX1276_LDRO_FORCE_ON;
#elif defined(CONFIG_SX1276_LDRO_FORCE_OFF)
    out_phy->ldro_mode             = SX1276_LDRO_FORCE_OFF;
#else
    out_phy->ldro_mode             = SX1276_LDRO_AUTO;
#endif

#if defined(CONFIG_SX1276_PA_PATH_RFO)
    out_phy->pa_path               = SX1276_PA_PATH_RFO;
#elif defined(CONFIG_SX1276_PA_PATH_BOOST)
    out_phy->pa_path               = SX1276_PA_PATH_BOOST;
#else
    out_phy->pa_path               = SX1276_PA_PATH_UNKNOWN;
#endif

#if defined(CONFIG_SX1276_RF_TX_ENABLE)
    out_phy->rf_tx_enabled         = true;
#else
    out_phy->rf_tx_enabled         = false;
#endif

    out_phy->tx_power_dbm          = (int8_t)CONFIG_SX1276_TX_POWER_DBM;
    out_phy->pa_ramp_us            = (uint16_t)CONFIG_SX1276_PA_RAMP_US;

#if defined(CONFIG_SX1276_OCP_ENABLE)
    out_phy->ocp_enabled           = true;
#else
    out_phy->ocp_enabled           = false;
#endif

    out_phy->ocp_current_limit_ma  = (uint8_t)CONFIG_SX1276_OCP_CURRENT_LIMIT_MA;

#if defined(CONFIG_SX1276_AGC_AUTO_ON)
    out_phy->agc_auto_on           = true;
#else
    out_phy->agc_auto_on           = false;
#endif

#if defined(CONFIG_SX1276_LNA_BOOST_HF)
    out_phy->lna_boost_hf          = true;
#else
    out_phy->lna_boost_hf          = false;
#endif

    out_phy->lna_gain_manual       = (uint8_t)CONFIG_SX1276_LNA_GAIN_MANUAL;

    return ESP_OK;
}

esp_err_t sx1276_config_validate(const sx1276_phy_config_t *conf)
{
    if (conf == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    // Validate Spreading Factor (SF7..SF12)
    if (conf->sf < SX1276_SF_7 || conf->sf > SX1276_SF_12) {
        return ESP_ERR_INVALID_ARG;
    }
    // Validate Bandwidth
    if (conf->bw != SX1276_BW_125K && conf->bw != SX1276_BW_250K && conf->bw != SX1276_BW_500K) {
        return ESP_ERR_INVALID_ARG;
    }
    // Validate Coding Rate
    if (conf->cr < SX1276_CR_4_5 || conf->cr > SX1276_CR_4_8) {
        return ESP_ERR_INVALID_ARG;
    }
    // Validate Channel and Frequency
    if (conf->channel_idx >= SX1276_VN920_CHANNEL_COUNT) {
        return ESP_ERR_INVALID_ARG;
    }
    if (conf->frequency_hz < 920000000U || conf->frequency_hz > 923000000U) {
        return ESP_ERR_INVALID_ARG;
    }
    // Validate Preamble (minimum 6 symbols per Semtech datasheet)
    if (conf->preamble_len < 6) {
        return ESP_ERR_INVALID_ARG;
    }
    // Validate Sync Word (0x34 is LoRaWAN, prohibited in private P2P network)
    if (conf->sync_word == 0x34) {
        return ESP_ERR_NOT_SUPPORTED;
    }
    // Validate PA path and power configuration
    if (conf->rf_tx_enabled) {
        if (conf->pa_path == SX1276_PA_PATH_UNKNOWN) {
            return ESP_ERR_INVALID_STATE; // Fail closed if PA path unverified
        }
        if (conf->pa_path == SX1276_PA_PATH_RFO) {
            if (conf->tx_power_dbm < -4 || conf->tx_power_dbm > 14) {
                return ESP_ERR_INVALID_ARG;
            }
        } else if (conf->pa_path == SX1276_PA_PATH_BOOST) {
            if (conf->tx_power_dbm < 2 || conf->tx_power_dbm > 20) {
                return ESP_ERR_INVALID_ARG;
            }
        }
    }
    // Validate OCP limit range (45 to 240 mA)
    if (conf->ocp_enabled) {
        if (conf->ocp_current_limit_ma < 45 || conf->ocp_current_limit_ma > 240) {
            return ESP_ERR_INVALID_ARG;
        }
    }

    return ESP_OK;
}

esp_err_t sx1276_register_plan_build(const sx1276_phy_config_t *conf,
                                     sx1276_register_plan_t *out_plan)
{
    esp_err_t err = sx1276_config_validate(conf);
    if (err != ESP_OK || out_plan == NULL) {
        return (err != ESP_OK) ? err : ESP_ERR_INVALID_ARG;
    }

    memset(out_plan, 0, sizeof(sx1276_register_plan_t));

    out_plan->reg_op_mode = SX1276_OPMODE_LONGRANGEMODE_LORA | SX1276_OPMODE_STANDBY;

    // Carrier frequency registers
    sx1276_frequency_to_frf(conf->frequency_hz,
                            &out_plan->reg_fr_msb,
                            &out_plan->reg_fr_mid,
                            &out_plan->reg_fr_lsb);

    // PA Configuration
    if (conf->pa_path == SX1276_PA_PATH_BOOST) {
        int8_t pwr = conf->tx_power_dbm;
        if (pwr < 2) pwr = 2;
        // User requested: comment lai phan gioi han phat 17dBm, toi da +20 dBm
        // if (pwr > 17) pwr = 17;
        if (pwr > 20) pwr = 20;

        if (pwr > 17) {
            // High Power (+20 dBm) mode on PA_BOOST per Semtech SX1276 datasheet Section 5.4.3
            // Pout = 20 - (15 - OutputPower) -> OutputPower = pwr - 5 (for +20 dBm, OutputPower = 15)
            uint8_t output_power = (uint8_t)(pwr - 5);
            out_plan->reg_pa_config = SX1276_PACONFIG_PASELECT_PA_BOOST | 0x70U | (output_power & 0x0FU);
            out_plan->reg_pa_dac = SX1276_PADAC_20DBM_ON;
        } else {
            // Standard PA_BOOST mode (+2 to +17 dBm)
            // Pout = 2 + OutputPower -> OutputPower = pwr - 2
            uint8_t output_power = (uint8_t)(pwr - 2);
            out_plan->reg_pa_config = SX1276_PACONFIG_PASELECT_PA_BOOST | 0x70U | (output_power & 0x0FU);
            out_plan->reg_pa_dac = SX1276_PADAC_DEFAULT;
        }
    } else if (conf->pa_path == SX1276_PA_PATH_RFO) {
        int8_t pwr = conf->tx_power_dbm;
        if (pwr < -4) pwr = -4;
        if (pwr > 14) pwr = 14;
        // Pout = Pmax - (15 - OutputPower), with Pmax = 14.8 dBm (MaxPower = 7)
        uint8_t output_power = (uint8_t)(pwr + 1);
        out_plan->reg_pa_config = SX1276_PACONFIG_PASELECT_RFO | 0x70U | (output_power & 0x0FU);
        out_plan->reg_pa_dac = SX1276_PADAC_DEFAULT;
    } else {
        out_plan->reg_pa_config = 0x00U; // Unknown / disabled
        out_plan->reg_pa_dac = SX1276_PADAC_DEFAULT;
    }

    // PA Ramp (40 us = 0x09)
    out_plan->reg_pa_ramp = 0x09U;

    // OCP (100 mA preset = 0x2B: OcpOn=1, OcpTrim=11)
    if (conf->ocp_enabled) {
        uint8_t trim = 11;
        if (conf->ocp_current_limit_ma <= 120) {
            trim = (conf->ocp_current_limit_ma - 45) / 5;
        } else {
            trim = (conf->ocp_current_limit_ma + 30) / 10;
        }
        out_plan->reg_ocp = SX1276_OCP_ON | (trim & SX1276_OCP_TRIM_MASK);
    } else {
        out_plan->reg_ocp = 0x00U;
    }

    // LNA: gain controlled by AGC when agc_auto_on=true; HF Boost default OFF (00b)
    uint8_t boost = conf->lna_boost_hf ? SX1276_LNA_BOOST_HF_ON : SX1276_LNA_BOOST_HF_DEFAULT;
    uint8_t gain = conf->agc_auto_on ? 0x01U : (conf->lna_gain_manual & 0x07U);
    out_plan->reg_lna = (uint8_t)((gain << 5) | boost);

    // ModemConfig1: (bw << 4) | (cr << 1) | (explicit_header ? 0 : 1)
    uint8_t bw_bits = (uint8_t)conf->bw;
    uint8_t cr_bits = (uint8_t)conf->cr;
    uint8_t implicit_hdr = conf->explicit_header ? 0x00U : 0x01U;
    out_plan->reg_modem_config_1 = (uint8_t)((bw_bits << 4) | (cr_bits << 1) | implicit_hdr);

    // ModemConfig2: (sf << 4) | (crc_on ? 0x04 : 0) | symb_timeout_msb
    uint8_t sf_bits = (uint8_t)conf->sf;
    uint8_t crc_bit = conf->payload_crc_on ? 0x04U : 0x00U;
    out_plan->reg_modem_config_2 = (uint8_t)((sf_bits << 4) | crc_bit);

    // ModemConfig3: LowDataRateOptimize & AgcAutoOn
    bool ldro_active = false;
    if (conf->ldro_mode == SX1276_LDRO_FORCE_ON) {
        ldro_active = true;
    } else if (conf->ldro_mode == SX1276_LDRO_AUTO) {
        // Calculate symbol duration: Ts = 2^SF / BW
        // If Ts > 16 ms, silicon requires LDRO = ON
        uint32_t bw_hz = 125000U;
        if (conf->bw == SX1276_BW_250K) bw_hz = 250000U;
        else if (conf->bw == SX1276_BW_500K) bw_hz = 500000U;

        uint32_t ts_us = ((1UL << conf->sf) * 1000000UL) / bw_hz;
        if (ts_us > 16000UL) {
            ldro_active = true;
        }
    }
    uint8_t mc3 = 0x00U;
    if (ldro_active) {
        mc3 |= SX1276_MC3_LOWDATARATEOPTIMIZE;
    }
    if (conf->agc_auto_on) {
        mc3 |= SX1276_MC3_AGCAUTOON;
    }
    out_plan->reg_modem_config_3 = mc3;

    // Symbol timeout LSB (100 symbols search default)
    out_plan->reg_symb_timeout_lsb = 0x64U;

    // Preamble length
    out_plan->reg_preamble_msb = (uint8_t)((conf->preamble_len >> 8) & 0xFFU);
    out_plan->reg_preamble_lsb = (uint8_t)(conf->preamble_len & 0xFFU);

    // Sync Word (0x12)
    out_plan->reg_sync_word = conf->sync_word;

    // Errata: bit 7 cleared in RegDetectOptimize (yielding 0x43 for SF7)
    out_plan->reg_detect_optimize = 0x43U;
    out_plan->reg_detection_threshold = SX1276_DETECTION_THRESHOLD_SF7_12;

    return ESP_OK;
}

esp_err_t sx1276_calculate_toa_us(const sx1276_phy_config_t *conf,
                                  uint8_t payload_len,
                                  uint32_t *out_toa_us)
{
    if (conf == NULL || out_toa_us == NULL) {
        return ESP_ERR_INVALID_ARG;
    }

    uint32_t bw_hz = 125000U;
    if (conf->bw == SX1276_BW_250K) bw_hz = 250000U;
    else if (conf->bw == SX1276_BW_500K) bw_hz = 500000U;

    uint32_t sf = conf->sf;
    // Ts in nanoseconds for higher precision: Ts_ns = (2^SF * 1e9) / BW
    uint64_t ts_ns = (((uint64_t)1U << sf) * 1000000000ULL) / bw_hz;

    // T_preamble = (N_preamble + 4.25) * Ts
    uint64_t t_preamble_ns = (uint64_t)((double)(conf->preamble_len + 4.25) * (double)ts_ns);

    // Payload symbols formulation
    int pl = (int)payload_len;
    int ih = conf->explicit_header ? 0 : 1;
    int crc = conf->payload_crc_on ? 1 : 0;
    int de = (conf->ldro_mode == SX1276_LDRO_FORCE_ON) ? 1 : 0;
    if (conf->ldro_mode == SX1276_LDRO_AUTO) {
        if ((ts_ns / 1000000ULL) > 16) {
            de = 1;
        }
    }
    int cr = (int)conf->cr; // 1 for 4/5

    int numerator = 8 * pl - 4 * (int)sf + 28 + 16 * crc - 20 * ih;
    int denominator = 4 * ((int)sf - 2 * de);

    int ceil_term = 0;
    if (numerator > 0 && denominator > 0) {
        ceil_term = (numerator + denominator - 1) / denominator;
    }
    if (ceil_term < 0) {
        ceil_term = 0;
    }

    int n_payload = 8 + ceil_term * (cr + 4);
    uint64_t t_payload_ns = (uint64_t)n_payload * ts_ns;

    uint64_t total_toa_us = (t_preamble_ns + t_payload_ns + 500ULL) / 1000ULL;
    *out_toa_us = (uint32_t)total_toa_us;

    return ESP_OK;
}
