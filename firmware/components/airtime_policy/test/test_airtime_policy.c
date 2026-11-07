/**
 * @file test_airtime_policy.c
 * @brief Unit tests for Pre-Transmit Duty Cycle and Airtime Enforcement Policy.
 *
 * Authority: Issue #13, Issue #179, C Coding Standard v2, contracts/radio-mac/specification.md.
 * Scope: Zero dynamic allocation, bounded execution, regulatory TX refusal, wrap protection.
 */

#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#include "airtime_policy.h"

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
 * @brief Verify nominal initialization and budget configuration.
 */
static int test_airtime_policy_init_nominal(void)
{
    /* 10 permille = 1.0% duty cycle -> 36,000 ms budget per 3,600,000 ms window */
    esp_err_t err = airtime_policy_init(10);
    ASSERT_EQUAL_INT(ESP_OK, err);
    ASSERT_EQUAL_UINT32(0, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(36000, airtime_policy_get_remaining_budget_ms());
    return 0;
}

/**
 * @brief Verify invalid initialization bounds fail closed.
 */
static int test_airtime_policy_init_bounds(void)
{
    /* 0 permille is invalid */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, airtime_policy_init(0));

    /* > 1000 permille (> 100%) is invalid */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, airtime_policy_init(1001));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_ARG, airtime_policy_init(65535));

    /* 1 permille (0.1%) -> 3,600 ms budget */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_init(1));
    ASSERT_EQUAL_UINT32(3600, airtime_policy_get_remaining_budget_ms());

    /* 1000 permille (100%) -> 3,600,000 ms budget */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_init(1000));
    ASSERT_EQUAL_UINT32(AIRTIME_POLICY_WINDOW_MS, airtime_policy_get_remaining_budget_ms());

    /* Restore default 10 permille */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_init(AIRTIME_POLICY_DEFAULT_PERMILLE));
    return 0;
}

/**
 * @brief Verify zero ToA packet check returns ESP_OK.
 */
static int test_airtime_policy_zero_toa(void)
{
    airtime_policy_reset();
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_check(0));
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(0));
    ASSERT_EQUAL_UINT32(0, airtime_policy_get_accumulated_tx_ms());
    return 0;
}

/**
 * @brief Verify incremental airtime recording and budget tracking.
 */
static int test_airtime_policy_record_incremental(void)
{
    airtime_policy_init(10); /* 36,000 ms budget */

    /* Packet 1: 50 ms */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_check(50));
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(50));
    ASSERT_EQUAL_UINT32(50, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(35950, airtime_policy_get_remaining_budget_ms());

    /* Packet 2: 150 ms */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_check(150));
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(150));
    ASSERT_EQUAL_UINT32(200, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(35800, airtime_policy_get_remaining_budget_ms());
    return 0;
}

/**
 * @brief Verify pre-transmit check strictly denies TX when budget exhausted.
 */
static int test_airtime_policy_budget_exhaustion(void)
{
    /* Use small 1 permille budget (3,600 ms) for crisp threshold verification */
    airtime_policy_init(1);

    /* Consume 3,500 ms */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_check(3500));
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(3500));
    ASSERT_EQUAL_UINT32(100, airtime_policy_get_remaining_budget_ms());

    /* 100 ms packet exactly meets budget -> allowed */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_check(100));

    /* 101 ms packet exceeds budget by 1 ms -> strictly denied */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(101));

    /* Record 100 ms to hit exactly 3,600 ms budget limit */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(100));
    ASSERT_EQUAL_UINT32(3600, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(0, airtime_policy_get_remaining_budget_ms());

    /* Any further transmission (>0 ms) MUST be rejected */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(1));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(25));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(100));
    return 0;
}

/**
 * @brief Verify regulatory duty limits apply equally to all message classes.
 * Emergency / Priority Alert frames MAY NEVER bypass the duty cycle ceiling.
 */
static int test_airtime_policy_no_alert_bypass(void)
{
    airtime_policy_init(1); /* 3,600 ms budget */

    /* Exhaust budget */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(3600));
    ASSERT_EQUAL_UINT32(0, airtime_policy_get_remaining_budget_ms());

    /*
     * Simulate diverse message types attempting transmission:
     * - Event DATA (e.g. 50 ms)
     * - Priority Alert (e.g. 80 ms)
     * - Maintenance Beacon (e.g. 100 ms)
     * - Unscheduled Retransmission (e.g. 50 ms)
     * ALL must fail-closed with ESP_ERR_INVALID_STATE.
     */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(50));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(80));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(100));
    return 0;
}

/**
 * @brief Verify integer wrap and clock overflow fail closed.
 */
static int test_airtime_policy_overflow_protection(void)
{
    airtime_policy_init(10); /* 36,000 ms budget */

    /* Recording extreme ToA must saturate without integer wrapping to 0 */
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(UINT32_MAX));
    ASSERT_EQUAL_UINT32(UINT32_MAX, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(0, airtime_policy_get_remaining_budget_ms());

    /* Pre-flight check MUST deny transmission */
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(1));
    ASSERT_EQUAL_INT(ESP_ERR_INVALID_STATE, airtime_policy_check(UINT32_MAX));
    return 0;
}

/**
 * @brief Verify window reset resets accumulator to 0.
 */
static int test_airtime_policy_reset(void)
{
    airtime_policy_init(10);
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_record_tx(15000));
    ASSERT_EQUAL_UINT32(15000, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(21000, airtime_policy_get_remaining_budget_ms());

    airtime_policy_reset();
    ASSERT_EQUAL_UINT32(0, airtime_policy_get_accumulated_tx_ms());
    ASSERT_EQUAL_UINT32(36000, airtime_policy_get_remaining_budget_ms());
    ASSERT_EQUAL_INT(ESP_OK, airtime_policy_check(36000));
    return 0;
}

int main(void)
{
    int failures = 0;
    printf("=== Starting airtime_policy Unit Tests ===\n");

    TEST_RUN(test_airtime_policy_init_nominal);
    TEST_RUN(test_airtime_policy_init_bounds);
    TEST_RUN(test_airtime_policy_zero_toa);
    TEST_RUN(test_airtime_policy_record_incremental);
    TEST_RUN(test_airtime_policy_budget_exhaustion);
    TEST_RUN(test_airtime_policy_no_alert_bypass);
    TEST_RUN(test_airtime_policy_overflow_protection);
    TEST_RUN(test_airtime_policy_reset);

    printf("=== airtime_policy Unit Tests Completed: %s (failures: %d) ===\n",
           failures == 0 ? "ALL PASSED" : "FAILED", failures);

    return failures;
}
