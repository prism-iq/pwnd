/**
 * L Investigation - C++ BLOOD Server
 *
 * The blood carries oxygen (data) throughout the body:
 * - HTTP server on port 9003
 * - /health - Health check
 * - /search - Full-text search
 *
 * Build: g++ -std=c++17 -O3 -pthread -o blood blood_server.cpp
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <thread>
#include <mutex>
#include <atomic>
#include <chrono>
#include <cstring>
#include <cmath>
#include <regex>

// Socket includes
#include <sys/socket.h>
#include <netinet/in.h>
#include <unistd.h>
#include <arpa/inet.h>

// =============================================================================
// CONFIGURATION
// =============================================================================

constexpr int DEFAULT_PORT = 9003;
constexpr int MAX_CONNECTIONS = 100;
constexpr int BUFFER_SIZE = 65536;

// =============================================================================
// INVERTED INDEX
// =============================================================================

struct SearchResult {
    int64_t id;
    float score;
    std::string title;
    std::string snippet;
};

class SearchIndex {
private:
    std::unordered_map<std::string, std::vector<std::pair<int64_t, float>>> index;
    std::unordered_map<int64_t, std::pair<std::string, std::string>> docs; // id -> (title, content)
    std::mutex mutex;
    std::atomic<size_t> doc_count{0};

    std::vector<std::string> tokenize(const std::string& text) {
        std::vector<std::string> tokens;
        std::string token;
        for (char c : text) {
            if (std::isalnum(c)) {
                token += std::tolower(c);
            } else if (!token.empty()) {
                if (token.length() >= 2) tokens.push_back(token);
                token.clear();
            }
        }
        if (!token.empty() && token.length() >= 2) tokens.push_back(token);
        return tokens;
    }

public:
    void add(int64_t id, const std::string& title, const std::string& content) {
        std::lock_guard<std::mutex> lock(mutex);
        docs[id] = {title, content};

        auto tokens = tokenize(title + " " + content);
        std::unordered_map<std::string, int> freq;
        for (const auto& t : tokens) freq[t]++;

        for (const auto& [word, count] : freq) {
            float tf = static_cast<float>(count) / tokens.size();
            index[word].emplace_back(id, tf);
        }
        doc_count++;
    }

    std::vector<SearchResult> search(const std::string& query, int limit = 20) {
        std::lock_guard<std::mutex> lock(mutex);

        auto terms = tokenize(query);
        std::unordered_map<int64_t, float> scores;

        for (const auto& term : terms) {
            auto it = index.find(term);
            if (it != index.end()) {
                float idf = std::log(1.0f + doc_count / static_cast<float>(it->second.size()));
                for (const auto& [id, tf] : it->second) {
                    scores[id] += tf * idf;
                }
            }
        }

        std::vector<std::pair<int64_t, float>> ranked(scores.begin(), scores.end());
        std::sort(ranked.begin(), ranked.end(),
            [](const auto& a, const auto& b) { return a.second > b.second; });

        std::vector<SearchResult> results;
        for (int i = 0; i < std::min(limit, static_cast<int>(ranked.size())); i++) {
            auto& [id, score] = ranked[i];
            auto& [title, content] = docs[id];
            std::string snippet = content.substr(0, std::min(size_t(200), content.size()));
            results.push_back({id, score, title, snippet});
        }
        return results;
    }

    size_t count() const { return doc_count; }
};

// Global index
SearchIndex g_index;
std::atomic<uint64_t> g_requests{0};
auto g_start_time = std::chrono::steady_clock::now();

// =============================================================================
// HTTP UTILITIES
// =============================================================================

std::string parse_json_field(const std::string& json, const std::string& field) {
    std::string key = "\"" + field + "\"";
    auto pos = json.find(key);
    if (pos == std::string::npos) return "";

    pos = json.find(":", pos);
    if (pos == std::string::npos) return "";

    pos = json.find_first_not_of(" \t\n", pos + 1);
    if (pos == std::string::npos) return "";

    if (json[pos] == '"') {
        auto end = json.find('"', pos + 1);
        return json.substr(pos + 1, end - pos - 1);
    }

    auto end = json.find_first_of(",}", pos);
    return json.substr(pos, end - pos);
}

std::string json_escape(const std::string& s) {
    std::string result;
    for (char c : s) {
        if (c == '"') result += "\\\"";
        else if (c == '\\') result += "\\\\";
        else if (c == '\n') result += "\\n";
        else if (c == '\r') result += "\\r";
        else if (c == '\t') result += "\\t";
        else result += c;
    }
    return result;
}

std::string http_response(int code, const std::string& body, const std::string& content_type = "application/json") {
    std::string status = (code == 200) ? "OK" : (code == 404) ? "Not Found" : "Error";
    std::ostringstream ss;
    ss << "HTTP/1.1 " << code << " " << status << "\r\n"
       << "Content-Type: " << content_type << "\r\n"
       << "Content-Length: " << body.size() << "\r\n"
       << "Access-Control-Allow-Origin: *\r\n"
       << "Connection: close\r\n\r\n"
       << body;
    return ss.str();
}

// =============================================================================
// REQUEST HANDLERS
// =============================================================================

std::string handle_health() {
    auto now = std::chrono::steady_clock::now();
    auto uptime = std::chrono::duration_cast<std::chrono::seconds>(now - g_start_time).count();

    std::ostringstream json;
    json << "{"
         << "\"status\":\"healthy\","
         << "\"service\":\"l-blood-cpp\","
         << "\"version\":\"1.0.0\","
         << "\"uptime\":" << uptime << ","
         << "\"requests\":" << g_requests << ","
         << "\"documents\":" << g_index.count()
         << "}";
    return http_response(200, json.str());
}

std::string handle_search(const std::string& body) {
    std::string query = parse_json_field(body, "query");
    int limit = 20;
    std::string limit_str = parse_json_field(body, "limit");
    if (!limit_str.empty()) limit = std::stoi(limit_str);

    auto results = g_index.search(query, limit);

    std::ostringstream json;
    json << "{\"results\":[";
    for (size_t i = 0; i < results.size(); i++) {
        if (i > 0) json << ",";
        json << "{"
             << "\"id\":" << results[i].id << ","
             << "\"score\":" << results[i].score << ","
             << "\"title\":\"" << json_escape(results[i].title) << "\","
             << "\"snippet\":\"" << json_escape(results[i].snippet) << "\""
             << "}";
    }
    json << "],\"total\":" << results.size() << ",\"query\":\"" << json_escape(query) << "\"}";
    return http_response(200, json.str());
}

std::string handle_extract(const std::string& body) {
    std::string text = parse_json_field(body, "text");

    // Simple pattern extraction (emails, dates, amounts)
    std::vector<std::pair<std::string, std::string>> patterns;

    // Email regex (simplified)
    std::regex email_re(R"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})");
    std::sregex_iterator it(text.begin(), text.end(), email_re);
    std::sregex_iterator end;
    while (it != end) {
        patterns.emplace_back("email", it->str());
        ++it;
    }

    // Money amounts
    std::regex money_re(R"(\$[\d,]+(?:\.\d{2})?)");
    it = std::sregex_iterator(text.begin(), text.end(), money_re);
    while (it != end) {
        patterns.emplace_back("amount", it->str());
        ++it;
    }

    std::ostringstream json;
    json << "{\"patterns\":[";
    for (size_t i = 0; i < patterns.size(); i++) {
        if (i > 0) json << ",";
        json << "{\"type\":\"" << patterns[i].first << "\",\"value\":\"" << json_escape(patterns[i].second) << "\"}";
    }
    json << "],\"count\":" << patterns.size() << "}";
    return http_response(200, json.str());
}

// =============================================================================
// HTTP SERVER
// =============================================================================

void handle_client(int client_fd) {
    char buffer[BUFFER_SIZE];
    ssize_t bytes = recv(client_fd, buffer, sizeof(buffer) - 1, 0);

    if (bytes <= 0) {
        close(client_fd);
        return;
    }

    buffer[bytes] = '\0';
    std::string request(buffer);
    g_requests++;

    // Parse request line
    std::istringstream stream(request);
    std::string method, path, version;
    stream >> method >> path >> version;

    // Find body (after \r\n\r\n)
    std::string body;
    auto body_start = request.find("\r\n\r\n");
    if (body_start != std::string::npos) {
        body = request.substr(body_start + 4);
    }

    // Route
    std::string response;
    if (path == "/health" && method == "GET") {
        response = handle_health();
    } else if (path == "/search" && method == "POST") {
        response = handle_search(body);
    } else if (path == "/extract" && method == "POST") {
        response = handle_extract(body);
    } else {
        response = http_response(404, "{\"error\":\"Not found\"}");
    }

    send(client_fd, response.c_str(), response.size(), 0);
    close(client_fd);
}

std::string parse_json_string_value(const std::string& json, size_t& pos) {
    // Skip to opening quote
    while (pos < json.size() && json[pos] != '"') pos++;
    if (pos >= json.size()) return "";
    pos++; // skip opening quote

    std::string result;
    while (pos < json.size() && json[pos] != '"') {
        if (json[pos] == '\\' && pos + 1 < json.size()) {
            pos++;
            if (json[pos] == 'n') result += '\n';
            else if (json[pos] == 'r') result += '\r';
            else if (json[pos] == 't') result += '\t';
            else if (json[pos] == '"') result += '"';
            else if (json[pos] == '\\') result += '\\';
            else result += json[pos];
        } else {
            result += json[pos];
        }
        pos++;
    }
    pos++; // skip closing quote
    return result;
}

void load_json_documents(const std::string& filepath) {
    std::cout << "Loading documents from " << filepath << "...\n";

    std::ifstream file(filepath);
    if (!file.is_open()) {
        std::cerr << "Failed to open " << filepath << "\n";
        return;
    }

    std::stringstream buffer;
    buffer << file.rdbuf();
    std::string json = buffer.str();
    file.close();

    size_t pos = 0;
    int loaded = 0;

    // Find array start
    while (pos < json.size() && json[pos] != '[') pos++;
    pos++;

    while (pos < json.size()) {
        // Find object start
        while (pos < json.size() && json[pos] != '{' && json[pos] != ']') pos++;
        if (pos >= json.size() || json[pos] == ']') break;
        pos++; // skip {

        int64_t id = 0;
        std::string title, content;

        // Parse object fields
        while (pos < json.size() && json[pos] != '}') {
            // Skip whitespace
            while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\n' || json[pos] == '\t' || json[pos] == ',')) pos++;
            if (json[pos] == '}') break;

            // Parse field name
            std::string field = parse_json_string_value(json, pos);

            // Skip colon
            while (pos < json.size() && json[pos] != ':') pos++;
            pos++;

            // Skip whitespace
            while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\n' || json[pos] == '\t')) pos++;

            if (field == "id") {
                // Parse number
                std::string num;
                while (pos < json.size() && (std::isdigit(json[pos]) || json[pos] == '-')) {
                    num += json[pos++];
                }
                id = std::stoll(num);
            } else if (field == "title") {
                title = parse_json_string_value(json, pos);
            } else if (field == "content") {
                content = parse_json_string_value(json, pos);
            }
        }

        if (id != 0 && !title.empty()) {
            g_index.add(id, title, content);
            loaded++;
            if (loaded % 1000 == 0) {
                std::cout << "  Loaded " << loaded << " documents...\n";
            }
        }

        pos++; // skip }
    }

    std::cout << "Loaded " << loaded << " documents from JSON\n";
}

void load_sample_data() {
    // Add some sample documents for testing
    g_index.add(1, "Jeffrey Epstein Flight Logs", "Private jet flights to Little St. James island with various passengers");
    g_index.add(2, "Ghislaine Maxwell Documents", "Court documents related to trafficking charges and trial testimony");
    g_index.add(3, "Financial Records", "Bank transfers and wire payments totaling $500,000 to various accounts");
    g_index.add(4, "Victim Testimony", "Sworn depositions from multiple accusers describing abuse patterns");
    g_index.add(5, "Property Holdings", "Real estate in New York, Palm Beach, New Mexico, Paris, and Virgin Islands");
    std::cout << "Loaded " << g_index.count() << " sample documents\n";
}

int main(int argc, char* argv[]) {
    int port = DEFAULT_PORT;
    std::string json_file;

    if (argc > 1) port = std::stoi(argv[1]);
    if (argc > 2) json_file = argv[2];

    std::cout << "╔═══════════════════════════════════════════════════════════╗\n";
    std::cout << "║       L Investigation - C++ BLOOD                         ║\n";
    std::cout << "║       High-speed search & pattern matching                ║\n";
    std::cout << "╠═══════════════════════════════════════════════════════════╣\n";
    std::cout << "║  Endpoints:                                               ║\n";
    std::cout << "║    GET  /health  - Health check                           ║\n";
    std::cout << "║    POST /search  - Full-text search                       ║\n";
    std::cout << "║    POST /extract - Pattern extraction                     ║\n";
    std::cout << "╚═══════════════════════════════════════════════════════════╝\n\n";

    if (!json_file.empty()) {
        load_json_documents(json_file);
    } else {
        load_sample_data();
    }

    // Create socket
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        std::cerr << "Failed to create socket\n";
        return 1;
    }

    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(port);

    if (bind(server_fd, (sockaddr*)&addr, sizeof(addr)) < 0) {
        std::cerr << "Failed to bind to port " << port << "\n";
        return 1;
    }

    if (listen(server_fd, MAX_CONNECTIONS) < 0) {
        std::cerr << "Failed to listen\n";
        return 1;
    }

    std::cout << "Blood server running on :" << port << "\n";

    while (true) {
        sockaddr_in client_addr{};
        socklen_t client_len = sizeof(client_addr);
        int client_fd = accept(server_fd, (sockaddr*)&client_addr, &client_len);

        if (client_fd >= 0) {
            std::thread(handle_client, client_fd).detach();
        }
    }

    close(server_fd);
    return 0;
}
