#define _POSIX_C_SOURCE 200809L

#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static uint64_t monotonic_ns(void) {
    struct timespec timestamp;
    if (clock_gettime(CLOCK_MONOTONIC, &timestamp) != 0) {
        perror("clock_gettime");
        exit(EXIT_FAILURE);
    }
    return (uint64_t)timestamp.tv_sec * UINT64_C(1000000000) +
           (uint64_t)timestamp.tv_nsec;
}

int main(int argc, char **argv) {
    uint64_t iterations = UINT64_C(100000000);
    if (argc == 2) {
        char *end = NULL;
        iterations = strtoull(argv[1], &end, 10);
        if (end == argv[1] || *end != '\0' || iterations == 0) {
            fprintf(stderr, "iterations must be a positive integer\n");
            return EXIT_FAILURE;
        }
    } else if (argc > 2) {
        fprintf(stderr, "usage: %s [iterations]\n", argv[0]);
        return EXIT_FAILURE;
    }

    uint64_t state = UINT64_C(0x6a09e667f3bcc909);
    const uint64_t started_ns = monotonic_ns();
    for (uint64_t index = 0; index < iterations; ++index) {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state += index ^ UINT64_C(0x9e3779b97f4a7c15);
    }
    const uint64_t elapsed_ns = monotonic_ns() - started_ns;

    printf("{\"elapsed_ns\":%" PRIu64 ",\"iterations\":%" PRIu64
           ",\"checksum\":\"%016" PRIx64 "\"}\n",
           elapsed_ns, iterations, state);
    return EXIT_SUCCESS;
}
