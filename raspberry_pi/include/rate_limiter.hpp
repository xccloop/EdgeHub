#pragma once
#include <unordered_map>
#include <cstdint>

// Token bucket rate limiter — per-IP request throttling.
// Call from the epoll thread only (not thread-safe for multi-threaded use).
class RateLimiter {
public:
    static constexpr int MAX_REQUESTS_PER_SEC = 10;
    static constexpr int BURST_SIZE = 20;
    static constexpr int CLEANUP_INTERVAL_MS = 60000;  // purge stale buckets every 60s

    // Returns true if the request from client_ip is allowed.
    // Converts IPv4 string to uint32_t for hashing.
    bool allow(uint32_t client_ip);
    bool allow(const char *ip_str);  // convenience: "192.168.1.100" → parsed internally

    // Purge buckets that haven't been used in > 120s.
    void cleanup(uint64_t now_ms);

    int total_rate_limited() const { return m_rate_limited_count; }

private:
    struct Bucket {
        double   tokens;
        uint64_t last_refill_ms;
    };
    std::unordered_map<uint32_t, Bucket> m_buckets;
    uint64_t m_last_cleanup_ms{0};
    int m_rate_limited_count{0};

    static uint32_t parse_ipv4(const char *s);
};
