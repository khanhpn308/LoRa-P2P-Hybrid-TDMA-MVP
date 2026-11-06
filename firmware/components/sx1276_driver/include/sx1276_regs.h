#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @file sx1276_regs.h
 * @brief Semtech SX1276 Register Map and Bitfield Definitions (MVP LoRa Mode).
 *
 * Sourced from Semtech SX1276 Datasheet Rev. 7 and docs/hardware/sx1276/SX1276_REGISTER_REFERENCE.md.
 */

/* =========================================================================
 * SX1276 Register Addresses
 * ========================================================================= */
#define SX1276_REG_FIFO                   0x00U
#define SX1276_REG_OP_MODE                0x01U
#define SX1276_REG_FR_MSB                 0x06U
#define SX1276_REG_FR_MID                 0x07U
#define SX1276_REG_FR_LSB                 0x08U
#define SX1276_REG_PA_CONFIG              0x09U
#define SX1276_REG_PA_RAMP                0x0AU
#define SX1276_REG_OCP                    0x0BU
#define SX1276_REG_LNA                    0x0CU
#define SX1276_REG_FIFO_ADDR_PTR          0x0DU
#define SX1276_REG_FIFO_TX_BASE_ADDR      0x0EU
#define SX1276_REG_FIFO_RX_BASE_ADDR      0x0FU
#define SX1276_REG_FIFO_RX_CURRENT_ADDR   0x10U
#define SX1276_REG_IRQ_FLAGS_MASK         0x11U
#define SX1276_REG_IRQ_FLAGS              0x12U
#define SX1276_REG_RX_NB_BYTES            0x13U
#define SX1276_REG_MODEM_STAT             0x18U
#define SX1276_REG_PKT_SNR_VALUE          0x19U
#define SX1276_REG_PKT_RSSI_VALUE         0x1AU
#define SX1276_REG_RSSI_VALUE             0x1BU
#define SX1276_REG_HOP_CHANNEL            0x1CU
#define SX1276_REG_MODEM_CONFIG_1         0x1DU
#define SX1276_REG_MODEM_CONFIG_2         0x1EU
#define SX1276_REG_SYMB_TIMEOUT_LSB       0x1FU
#define SX1276_REG_PREAMBLE_MSB           0x20U
#define SX1276_REG_PREAMBLE_LSB           0x21U
#define SX1276_REG_PAYLOAD_LENGTH         0x22U
#define SX1276_REG_MAX_PAYLOAD_LENGTH     0x23U
#define SX1276_REG_FIFO_RX_BYTE_ADDR      0x25U
#define SX1276_REG_MODEM_CONFIG_3         0x26U
#define SX1276_REG_DETECT_OPTIMIZE        0x31U
#define SX1276_REG_DETECTION_THRESHOLD    0x37U
#define SX1276_REG_SYNC_WORD              0x39U
#define SX1276_REG_DIO_MAPPING_1          0x40U
#define SX1276_REG_DIO_MAPPING_2          0x41U
#define SX1276_REG_VERSION                0x42U
#define SX1276_REG_PA_DAC                 0x4DU

/* Expected silicon version */
#define SX1276_CHIP_VERSION_EXPECTED      0x12U

/* =========================================================================
 * RegOpMode (0x01) Bitfields
 * ========================================================================= */
#define SX1276_OPMODE_LONGRANGEMODE_LORA   0x80U
#define SX1276_OPMODE_LONGRANGEMODE_FSK    0x00U
#define SX1276_OPMODE_ACCESSSHAREDREG_LORA 0x00U
#define SX1276_OPMODE_LOWFREQUENCY_HF      0x00U
#define SX1276_OPMODE_MODE_MASK            0x07U

#define SX1276_OPMODE_SLEEP                0x00U
#define SX1276_OPMODE_STANDBY              0x01U
#define SX1276_OPMODE_FSTX                 0x02U
#define SX1276_OPMODE_TX                   0x03U
#define SX1276_OPMODE_FSRX                 0x04U
#define SX1276_OPMODE_RXCONTINUOUS         0x05U
#define SX1276_OPMODE_RXSINGLE             0x06U
#define SX1276_OPMODE_CAD                  0x07U

/* =========================================================================
 * RegIrqFlags (0x12) & RegIrqFlagsMask (0x11)
 * ========================================================================= */
#define SX1276_IRQ_RXTIMEOUT               0x80U
#define SX1276_IRQ_RXDONE                  0x40U
#define SX1276_IRQ_PAYLOADCRCERROR         0x20U
#define SX1276_IRQ_VALIDHEADER             0x10U
#define SX1276_IRQ_TXDONE                  0x08U
#define SX1276_IRQ_CADDONE                 0x04U
#define SX1276_IRQ_FHSSCHANGECHANNEL       0x02U
#define SX1276_IRQ_CADDETECTED             0x01U

/* Targeted clear mask for RX packet servicing (RxDone | PayloadCrcError | ValidHeader) */
#define SX1276_IRQ_RX_TARGETED_CLEAR_MASK  0x70U

/* =========================================================================
 * RegModemStat (0x18)
 * ========================================================================= */
#define SX1276_MODEMSTAT_MODEM_CLEAR       0x10U
#define SX1276_MODEMSTAT_HEADERINFOVALID   0x08U
#define SX1276_MODEMSTAT_RXONGOING         0x04U
#define SX1276_MODEMSTAT_SIGNALSYNC        0x02U
#define SX1276_MODEMSTAT_SIGNALDETECT      0x01U

/* =========================================================================
 * RegHopChannel (0x1C)
 * ========================================================================= */
#define SX1276_HOPCHANNEL_PLL_TIMEOUT      0x80U
#define SX1276_HOPCHANNEL_CRCONPAYLOAD     0x40U

/* =========================================================================
 * RegDioMapping1 (0x40) - DIO0 Mapping
 * ========================================================================= */
#define SX1276_DIOMAPPING1_DIO0_MASK       0xC0U
#define SX1276_DIOMAPPING1_DIO0_RXDONE     0x00U
#define SX1276_DIOMAPPING1_DIO0_TXDONE     0x40U
#define SX1276_DIOMAPPING1_DIO0_CADDONE    0x80U

/* =========================================================================
 * RegPaConfig (0x09)
 * ========================================================================= */
#define SX1276_PACONFIG_PASELECT_PA_BOOST  0x80U
#define SX1276_PACONFIG_PASELECT_RFO       0x00U
#define SX1276_PACONFIG_MAX_POWER_MASK     0x70U
#define SX1276_PACONFIG_OUTPUT_POWER_MASK  0x0FU

/* =========================================================================
 * RegOcp (0x0B)
 * ========================================================================= */
#define SX1276_OCP_ON                      0x20U
#define SX1276_OCP_TRIM_MASK               0x1FU

/* =========================================================================
 * RegLna (0x0C)
 * ========================================================================= */
#define SX1276_LNA_GAIN_MASK               0xE0U
#define SX1276_LNA_BOOST_HF_MASK           0x03U
#define SX1276_LNA_BOOST_HF_DEFAULT        0x00U
#define SX1276_LNA_BOOST_HF_ON             0x03U

/* =========================================================================
 * RegModemConfig3 (0x26)
 * ========================================================================= */
#define SX1276_MC3_LOWDATARATEOPTIMIZE     0x08U
#define SX1276_MC3_AGCAUTOON               0x04U

/* =========================================================================
 * Errata & Detection Optimize (0x31, 0x37)
 * ========================================================================= */
#define SX1276_DETECT_OPTIMIZE_AUTO_IF_MASK 0x80U
#define SX1276_DETECT_OPTIMIZE_SF7_12       0x03U
#define SX1276_DETECTION_THRESHOLD_SF7_12   0x0AU

#ifdef __cplusplus
}
#endif
