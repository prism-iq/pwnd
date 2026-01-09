/**
 * L Investigation - C++ SYNAPSES
 *
 * The synapses transform signals between neurons:
 * - Takes input from any language (Rust, Go, Python, Node)
 * - Transforms into hard, reliable, blazing-fast operations
 * - Returns perfectly formatted results, every time
 *
 * Compiled to shared library for FFI - the universal bridge
 */

#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <sstream>
#include <regex>
#include <cstring>
#include <cmath>

// =============================================================================
// DATA STRUCTURES
// =============================================================================

struct SearchResult {
    int64_t id;
    float score;
    std::string snippet;
    int64_t timestamp;
};

struct Document {
    int64_t id;
    std::string content;
    std::string subject;
    std::string sender;
    int64_t timestamp;
};

// =============================================================================
// INVERTED INDEX
// =============================================================================

class InvertedIndex {
private:
    std::unordered_map<std::string, std::vector<std::pair<int64_t, float>>> index;
    std::unordered_map<int64_t, Document> documents;
    std::mutex mutex;
    std::atomic<size_t> doc_count{0};

    std::vector<std::string> tokenize(const std::string& text) {
        std::vector<std::string> tokens;
        std::string token;
        for (char c : text) {
            if (std::isalnum(c)) {
                token += std::tolower(c);
            } else if (!token.empty()) {
                if (token.length() >= 2) {
                    tokens.push_back(token);
                }
                token.clear();
            }
        }
        if (!token.empty() && token.length() >= 2) {
            tokens.push_back(token);
        }
        return tokens;
    }

public:
    void add_document(const Document& doc) {
        std::lock_guard<std::mutex> lock(mutex);

        documents[doc.id] = doc;

        // Index content
        std::string full_text = doc.subject + " " + doc.content + " " + doc.sender;
        auto tokens = tokenize(full_text);

        std::unordered_map<std::string, int> term_freq;
        for (const auto& token : tokens) {
            term_freq[token]++;
        }

        for (const auto& [term, freq] : term_freq) {
            float tf = 1.0f + std::log(freq);
            index[term].push_back({doc.id, tf});
        }

        doc_count++;
    }

    std::vector<SearchResult> search(const std::string& query, int limit = 20) {
        auto tokens = tokenize(query);
        std::unordered_map<int64_t, float> scores;

        for (const auto& token : tokens) {
            auto it = index.find(token);
            if (it != index.end()) {
                float idf = std::log(1.0f + doc_count / (1.0f + it->second.size()));
                for (const auto& [doc_id, tf] : it->second) {
                    scores[doc_id] += tf * idf;
                }
            }
        }

        std::vector<std::pair<int64_t, float>> sorted_scores(scores.begin(), scores.end());
        std::partial_sort(sorted_scores.begin(),
                         sorted_scores.begin() + std::min((size_t)limit, sorted_scores.size()),
                         sorted_scores.end(),
                         [](const auto& a, const auto& b) { return a.second > b.second; });

        std::vector<SearchResult> results;
        for (size_t i = 0; i < std::min((size_t)limit, sorted_scores.size()); i++) {
            auto& doc = documents[sorted_scores[i].first];
            results.push_back({
                doc.id,
                sorted_scores[i].second,
                doc.content.substr(0, 200),
                doc.timestamp
            });
        }

        return results;
    }

    size_t size() const { return doc_count; }
};

// =============================================================================
// PATTERN MATCHER (SIMD-optimized where possible)
// =============================================================================

class PatternMatcher {
private:
    std::vector<std::regex> patterns;
    std::vector<std::string> pattern_names;

public:
    void add_pattern(const std::string& name, const std::string& regex_str) {
        patterns.push_back(std::regex(regex_str, std::regex::icase | std::regex::optimize));
        pattern_names.push_back(name);
    }

    std::vector<std::pair<std::string, std::string>> match_all(const std::string& text) {
        std::vector<std::pair<std::string, std::string>> matches;

        for (size_t i = 0; i < patterns.size(); i++) {
            std::smatch match;
            std::string::const_iterator start = text.begin();
            while (std::regex_search(start, text.end(), match, patterns[i])) {
                matches.push_back({pattern_names[i], match.str()});
                start = match[0].second;
            }
        }

        return matches;
    }
};

// =============================================================================
// GLOBAL INSTANCES
// =============================================================================

static InvertedIndex g_index;
static PatternMatcher g_matcher;
static std::atomic<bool> g_initialized{false};

// =============================================================================
// C FFI INTERFACE (for Rust/Go/Node bindings)
// =============================================================================

extern "C" {

// Initialize the search engine
int l_search_init() {
    if (g_initialized) return 0;

    // Add criminal patterns
    g_matcher.add_pattern("person", R"(\b[A-Z][a-z]{2,15} [A-Z][a-z]{2,15}\b)");
    g_matcher.add_pattern("amount", R"(\$[\d,]+(?:\.\d{2})?)");
    g_matcher.add_pattern("date", R"(\b\d{4}-\d{2}-\d{2}\b)");
    g_matcher.add_pattern("email", R"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})");

    g_initialized = true;
    return 0;
}

// Add document to index
int l_search_add(int64_t id, const char* content, const char* subject,
                 const char* sender, int64_t timestamp) {
    Document doc{id, content, subject, sender, timestamp};
    g_index.add_document(doc);
    return 0;
}

// Search documents
typedef struct {
    int64_t id;
    float score;
    char snippet[256];
} CSearchResult;

int l_search_query(const char* query, CSearchResult* results, int max_results) {
    auto cpp_results = g_index.search(query, max_results);

    for (size_t i = 0; i < cpp_results.size() && i < (size_t)max_results; i++) {
        results[i].id = cpp_results[i].id;
        results[i].score = cpp_results[i].score;
        strncpy(results[i].snippet, cpp_results[i].snippet.c_str(), 255);
        results[i].snippet[255] = '\0';
    }

    return cpp_results.size();
}

// Extract patterns from text
typedef struct {
    char type[32];
    char value[256];
} CPattern;

int l_search_extract(const char* text, CPattern* patterns, int max_patterns) {
    auto matches = g_matcher.match_all(text);

    for (size_t i = 0; i < matches.size() && i < (size_t)max_patterns; i++) {
        strncpy(patterns[i].type, matches[i].first.c_str(), 31);
        patterns[i].type[31] = '\0';
        strncpy(patterns[i].value, matches[i].second.c_str(), 255);
        patterns[i].value[255] = '\0';
    }

    return matches.size();
}

// Get index stats
int64_t l_search_count() {
    return g_index.size();
}

// =============================================================================
// SYNAPSE TRANSFORMERS - Universal signal processing
// =============================================================================

// Hash text for deduplication (FNV-1a)
uint64_t l_synapse_hash(const char* text) {
    uint64_t hash = 14695981039346656037ULL;
    while (*text) {
        hash ^= (uint8_t)*text++;
        hash *= 1099511628211ULL;
    }
    return hash;
}

// Normalize text for comparison (lowercase, strip whitespace)
int l_synapse_normalize(const char* input, char* output, int max_len) {
    int j = 0;
    bool last_space = true;

    for (int i = 0; input[i] && j < max_len - 1; i++) {
        char c = input[i];
        if (std::isalnum(c)) {
            output[j++] = std::tolower(c);
            last_space = false;
        } else if (!last_space && j < max_len - 1) {
            output[j++] = ' ';
            last_space = true;
        }
    }

    // Trim trailing space
    if (j > 0 && output[j-1] == ' ') j--;
    output[j] = '\0';
    return j;
}

// Calculate similarity between two strings (Jaccard coefficient)
float l_synapse_similarity(const char* a, const char* b) {
    std::unordered_set<std::string> set_a, set_b;

    // Tokenize both strings
    auto tokenize = [](const char* s) {
        std::unordered_set<std::string> tokens;
        std::string token;
        while (*s) {
            if (std::isalnum(*s)) {
                token += std::tolower(*s);
            } else if (!token.empty()) {
                if (token.length() >= 2) tokens.insert(token);
                token.clear();
            }
            s++;
        }
        if (!token.empty() && token.length() >= 2) tokens.insert(token);
        return tokens;
    };

    set_a = tokenize(a);
    set_b = tokenize(b);

    if (set_a.empty() || set_b.empty()) return 0.0f;

    // Calculate intersection
    size_t intersection = 0;
    for (const auto& t : set_a) {
        if (set_b.count(t)) intersection++;
    }

    // Jaccard = |A ∩ B| / |A ∪ B|
    size_t union_size = set_a.size() + set_b.size() - intersection;
    return (float)intersection / (float)union_size;
}

// Extract numeric values from text
typedef struct {
    double value;
    char unit[16];
} CNumeric;

int l_synapse_numbers(const char* text, CNumeric* results, int max_results) {
    static std::regex num_regex(R"([\$€£]?([\d,]+(?:\.\d+)?)\s*([KkMmBb](?:illion)?|%|USD|EUR)?)");
    std::string str(text);
    std::smatch match;
    int count = 0;

    auto start = str.cbegin();
    while (std::regex_search(start, str.cend(), match, num_regex) && count < max_results) {
        std::string num_str = match[1].str();
        // Remove commas
        num_str.erase(std::remove(num_str.begin(), num_str.end(), ','), num_str.end());

        double val = std::stod(num_str);
        std::string unit = match[2].str();

        // Apply multiplier
        if (unit.find('K') != std::string::npos || unit.find('k') != std::string::npos) val *= 1000;
        else if (unit.find('M') != std::string::npos || unit.find('m') != std::string::npos) val *= 1000000;
        else if (unit.find('B') != std::string::npos || unit.find('b') != std::string::npos) val *= 1000000000;

        results[count].value = val;
        strncpy(results[count].unit, unit.c_str(), 15);
        results[count].unit[15] = '\0';
        count++;

        start = match[0].second;
    }

    return count;
}

// Compress text for transmission (simple RLE for repeated chars)
int l_synapse_compress(const char* input, char* output, int max_len) {
    int j = 0;
    int i = 0;

    while (input[i] && j < max_len - 4) {
        char c = input[i];
        int count = 1;

        while (input[i + count] == c && count < 255) count++;

        if (count >= 4) {
            output[j++] = '\x1b';  // escape
            output[j++] = (char)count;
            output[j++] = c;
        } else {
            for (int k = 0; k < count && j < max_len - 1; k++) {
                output[j++] = c;
            }
        }
        i += count;
    }

    output[j] = '\0';
    return j;
}

// Version info
const char* l_synapse_version() {
    return "1.0.0-synapses";
}

} // extern "C"
