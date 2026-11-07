/**
 * @file test_tdma_common.c
 * @brief Unit tests for TDMA Common Timing & Slot Layout Definitions (Profile P-10S-15).
 *
 * Authority: Issue #13, Issue #181, contracts/radio-mac/tdma-schedule.md, C Coding Standard v2.
 * Scope: Superframe, subframe, and slot timing calculations, drift guard formulas, parameter bounds.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#include "tdma_common.h"

#define TEST_RUN(name) do { \
    printf("Running %s ... ", #name); \
    if (name() == 0) { \
        printf("PASSED\n"); \
    } else { \
        printf("FAILED\n"); \
        failures++; \
    } \
} while (0)

#define ASSERT_TRUE(cond) do { \
    if (!(cond)) { \
        fprintf(stderr, "\nAssertion failed: %s at %s:%d\n", #cond, __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_FALSE(cond) do { \
    if (cond) { \
        fprintf(stderr, "\nAssertion failed: NOT %s at %s:%d\n", #cond, __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_INT(expected, actual) do { \
    if ((int)(expected) != (int)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %d, got %d) at %s:%d\n", \
                #expected, #actual, (int)(expected), (int)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

#define ASSERT_EQUAL_UINT32(expected, actual) do { \
    if ((uint32_t)(expected) != (uint32_t)(actual)) { \
        fprintf(stderr, "\nAssertion failed: %s == %s (expected %lu, got %lu) at %s:%d\n", \
                #expected, #actual, (unsigned long)(expected), (unsigned long)(actual), __FILE__, __LINE__); \
        return -1; \
    } \
} while (0)

/**
 * @brief Test initialization lifecycle.
 */
static int test_tdma_common_init(void)
{
    esp_err_t err = tdma_common_init();
    ASSERT_EQUAL_INT(ESP_OK, err);
    return 0;
}

/**
 * @brief Test slot ID validity across all ranges.
 */
static int test_tdma_is_valid_slot_id(void)
{
    /* Out of bounds below */
    ASSERT_FALSE(tdma_is_valid_slot_id(0));

    /* Valid dedicated DATA slots #1 through #15 */
    for (uint8_t i = 1; i <= TDMA_TOTAL_DATA_SLOTS; i++) {
        ASSERT_TRUE(tdma_is_valid_slot_id(i));
    }

    /* Out of bounds above */
    ASSERT_FALSE(tdma_is_valid_slot_id(16));
    ASSERT_FALSE(tdma_is_valid_slot_id(17));
    ASSERT_FALSE(tdma_is_valid_slot_id(255));
    return 0;
}

/**
 * @brief Test slot start offset calculations for all 15 slots in Profile P-10S-15.
 * Formula:
 *   subframe_idx = (slot_id - 1) / 3;
 *   slot_in_subframe = (slot_id - 1) % 3;
 *   offset = 2000 * subframe_idx + 650 + 400 * slot_in_subframe
 */
static int test_tdma_get_slot_start_offset_nominal(void)
{
    static const uint32_t expected_offsets[15] = {
        650,   /* Slot 1:  SF0, Slot 0 */
        1050,  /* Slot 2:  SF0, Slot 1 */
        1450,  /* Slot 3:  SF0, Slot 2 */
        2650,  /* Slot 4:  SF1, Slot 0 */
        3050,  /* Slot 5:  SF1, Slot 1 */
        3450,  /* Slot 6:  SF1, Slot 2 */
        4650,  /* Slot 7:  SF2, Slot 0 */
        5050,  /* Slot 8:  SF2, Slot 1 */
        5450,  /* Slot 9:  SF2, Slot 2 */
        6650,  /* Slot 10: SF3, Slot 0 */
        7050,  /* Slot 11: SF3, Slot 1 */
        7450,  /* Slot 12: SF3, Slot 2 */
        8650,  /* Slot 13: SF4, Slot 0 */
        9050,  /* Slot 14: SF4, Slot 1 */
        9450,  /* Slot 15: SF4, Slot 2 */
    };

    for (uint8_t slot_id = 1; slot_id <= 15; slot_id++) {
        uint32_t offset_ms = 0;
        esp_err_t err = tdma_get_slot_start_offset_ms(slot_id, &offset_ms);
        ASSERT_EQUAL_INT(ESP_OK, err);
        ASSERT_EQUAL_UINT32(expected_offsets[slot_id - 1], offset_ms);

        /* Confirm within subframe DATA section boundaries */
        uint32_t subframe_idx = (uint32_t)(slot_id - 1) / TDMA_DATA_SLOTS_PER_SUBFRAME;
        uint32_t sf_data_start = (subframe_idx * TDMA_SUBFRAME_MS) + TDMA_DATA_SECTION_START_MS;
        uint32_t sf_data_end = sf_data_start + (TDMA_DATA_SLOTS_PER_SUBFRAME * TDMA_SLOT_DURATION_MS);
        ASSERT_TRUE(offset_ms >= sf_data_start);
        ASSERT_TRUE((offset_ms + TDMA_SLOT_DURATION_MS) <= sf_data_end);
    }

    return 0;
}

/**
 * @brief Test negative slot offset queries (invalid ID, NULL pointer).
 */
static int test_tdma_get_slot_start_offset_negative(void)
{
    uint32_t offset_ms = 0;

    /* Invalid slot_id = 0 */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, tdma_get_slot_start_offset_ms(0, &offset_ms));

    /* Invalid slot_id = 16 */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, tdma_get_slot_start_offset_ms(16, &offset_ms));

    /* Invalid slot_id = 255 */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, tdma_get_slot_start_offset_ms(255, &offset_ms));

    /* NULL output pointer */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, tdma_get_slot_start_offset_ms(1, NULL));
    return 0;
}

/**
 * @brief Test bilateral clock drift guard calculations.
 * Formula: drift_us = 2 * drift_ppm * interval_s; drift_ms = (drift_us + 999) / 1000; return drift_ms + 5ms.
 */
static int test_tdma_calculate_drift_guard(void)
{
    /* Zero drift -> minimum 5 ms base safety guard */
    ASSERT_EQUAL_UINT32(5, tdma_calculate_drift_guard_ms(0, 0));
    ASSERT_EQUAL_UINT32(5, tdma_calculate_drift_guard_ms(0, 100));

    /* 20 ppm drift over 10 seconds:
     * drift_us = 2 * 20 * 10 = 400 us -> drift_ms = (400 + 999)/1000 = 1 ms -> guard = 1 + 5 = 6 ms */
    ASSERT_EQUAL_UINT32(6, tdma_calculate_drift_guard_ms(20, 10));

    /* 40 ppm drift over 300 seconds (Maintenance Superframe):
     * drift_us = 2 * 40 * 300 = 24,000 us -> drift_ms = (24000 + 999)/1000 = 24 ms -> guard = 24 + 5 = 29 ms */
    ASSERT_EQUAL_UINT32(29, tdma_calculate_drift_guard_ms(40, 300));

    /* 50 ppm drift over 600 seconds:
     * drift_us = 2 * 50 * 600 = 60,000 us -> drift_ms = 60 ms -> guard = 60 + 5 = 65 ms */
    ASSERT_EQUAL_UINT32(65, tdma_calculate_drift_guard_ms(50, 600));

    return 0;
}

int main(void)
{
    int failures = 0;
    printf("=== Starting tdma_common Unit Tests ===\n");

    TEST_RUN(test_tdma_common_init);
    TEST_RUN(test_tdma_is_valid_slot_id);
    TEST_RUN(test_tdma_get_slot_start_offset_nominal);
    TEST_RUN(test_tdma_get_slot_start_offset_negative);
    TEST_RUN(test_tdma_calculate_drift_guard);

    printf("=== tdma_common Unit Tests Completed: %s (failures: %d) ===\n",
           failures == 0 ? "ALL PASSED" : "FAILED", failures);

    return failures;
}
