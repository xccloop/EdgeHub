#include "rate_limiter.hpp"
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <ctime>

uint32_t RateLimiter::parse_ipv4(const char *s) {
    unsigned int a = 0, b = 0, c = 0, d = 0;
    if (sscanf(s, "%u.%u.%u.%u", &a, &b, &c, &d) == 4)
        return (a << 24) | (b << 16) | (c << 8) | d;
    // fallback: hash the string
    uint32_t h = 0;
    while (*s) h = h * 31 + (unsigned char)*s++;
    return h;
}

bool RateLimiter::allow(uint32_t client_ip) {
    uint64_t now_ms = 0;
    { /* get time — lightweight, implementation in time_util */
        struct timespec ts;
        clock_gettime(CLOCK_MONOTONIC, &ts);
        now_ms = (uint64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
    }

    auto it = m_buckets.find(client_ip);
    if (it == m_buckets.end()) {
        // New bucket — start with full tokens
        m_buckets[client_ip] = {(double)BURST_SIZE - 1, now_ms};
        return true;
    }

    Bucket &b = it->second;

    // Refill tokens
    uint64_t elapsed = now_ms - b.last_refill_ms;
    if (elapsed > 0) {
        b.tokens += (double)elapsed * MAX_REQUESTS_PER_SEC / 1000.0;
        if (b.tokens > BURST_SIZE) b.tokens = BURST_SIZE;
    }
    b.last_refill_ms = now_ms;

    if (b.tokens >= 1.0) {
        b.tokens -= 1.0;
        return true;
    }

    m_rate_limited_count++;
    return false;
}

bool RateLimiter::allow(const char *ip_str) {
    return allow(parse_ipv4(ip_str));
}

void RateLimiter::cleanup(uint64_t now_ms) {
    if (m_last_cleanup_ms == 0 ||
        (now_ms - m_last_cleanup_ms) < (uint64_t)CLEANUP_INTERVAL_MS) return;
    m_last_cleanup_ms = now_ms;

    auto it = m_buckets.begin();
    while (it != m_buckets.end()) {
        if (now_ms - it->second.last_refill_ms > 120000) {
            it = m_buckets.erase(it);
        } else {
            ++it;
        }
    }
}
