#ifndef BENCH_CONSOLE_H
#define BENCH_CONSOLE_H
#include <stdbool.h>
/* app_main/task context only; owns stdin and all local event state until
 * reboot. Runs indefinitely with a one-tick yield on each iteration.
 * gateway selects local ingress bench mode; false selects button bench mode.
 * No RF, persistence, network, GPIO or ISR operations. No pointer ownership. */
void bench_console_run_bench(bool gateway);
#endif
