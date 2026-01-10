/**
 * HybridCore Text Processor - High Performance C++ Module
 *
 * Ultra-fast text processing for document indexing
 * Compiles to native binary for maximum speed
 *
 * Build: g++ -O3 -std=c++17 -o text_processor text_processor.cpp
 */

#include <iostream>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <algorithm>
#include <chrono>
#include <regex>
#include <cctype>
#include <cmath>

// ═══════════════════════════════════════════════════════════════════
// STOPWORDS
// ═══════════════════════════════════════════════════════════════════

const std::unordered_set<std::string> STOPWORDS_EN = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "must", "shall", "can", "to", "of", "in",
    "for", "on", "with", "at", "by", "from", "as", "into", "through",
    "and", "but", "or", "nor", "so", "yet", "both", "either", "neither",
    "not", "only", "than", "too", "very", "just", "also", "now", "this",
    "that", "these", "those", "i", "you", "he", "she", "it", "we", "they"
};

const std::unordered_set<std::string> STOPWORDS_FR = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "est", "sont",
    "a", "au", "aux", "ce", "cette", "ces", "qui", "que", "quoi", "dont",
    "ou", "mais", "donc", "car", "ni", "ne", "pas", "plus", "moins", "tres",
    "pour", "par", "sur", "sous", "dans", "avec", "sans", "chez", "vers",
    "je", "tu", "il", "elle", "nous", "vous", "ils", "elles", "on", "se"
};

// ═══════════════════════════════════════════════════════════════════
// STRING UTILITIES
// ═══════════════════════════════════════════════════════════════════

std::string toLower(const std::string& str) {
    std::string result = str;
    std::transform(result.begin(), result.end(), result.begin(), ::tolower);
    return result;
}

std::string normalize(const std::string& str) {
    std::string result;
    result.reserve(str.size());

    for (char c : str) {
        if (std::isalnum(c) || c == ' ' || c == '\n') {
            result += std::tolower(c);
        } else if (std::ispunct(c)) {
            result += ' ';
        }
    }
    return result;
}

std::vector<std::string> tokenize(const std::string& text) {
    std::vector<std::string> tokens;
    std::istringstream stream(text);
    std::string token;

    while (stream >> token) {
        if (token.length() > 1) {
            tokens.push_back(token);
        }
    }
    return tokens;
}

// ═══════════════════════════════════════════════════════════════════
// TEXT ANALYSIS
// ═══════════════════════════════════════════════════════════════════

struct TextStats {
    size_t charCount;
    size_t wordCount;
    size_t sentenceCount;
    size_t uniqueWords;
    double avgWordLength;
    double lexicalDiversity;
    std::string detectedLanguage;
};

struct WordFrequency {
    std::string word;
    int count;
    double tf;
};

class TextProcessor {
private:
    std::unordered_map<std::string, int> wordFreq;
    std::vector<std::string> tokens;
    std::string normalizedText;

public:
    TextStats analyze(const std::string& text) {
        TextStats stats;
        auto start = std::chrono::high_resolution_clock::now();

        // Normalize and tokenize
        normalizedText = normalize(text);
        tokens = tokenize(normalizedText);

        // Basic counts
        stats.charCount = text.length();
        stats.wordCount = tokens.size();

        // Sentence count (simple heuristic)
        stats.sentenceCount = std::count_if(text.begin(), text.end(),
            [](char c) { return c == '.' || c == '!' || c == '?'; });
        if (stats.sentenceCount == 0) stats.sentenceCount = 1;

        // Word frequency and unique words
        wordFreq.clear();
        size_t totalLength = 0;

        for (const auto& token : tokens) {
            wordFreq[token]++;
            totalLength += token.length();
        }

        stats.uniqueWords = wordFreq.size();
        stats.avgWordLength = tokens.empty() ? 0 :
            static_cast<double>(totalLength) / tokens.size();

        // Lexical diversity (type-token ratio)
        stats.lexicalDiversity = tokens.empty() ? 0 :
            static_cast<double>(stats.uniqueWords) / tokens.size();

        // Language detection
        stats.detectedLanguage = detectLanguage();

        auto end = std::chrono::high_resolution_clock::now();
        auto duration = std::chrono::duration_cast<std::chrono::microseconds>(end - start);

        std::cerr << "[C++] Processed " << stats.wordCount << " words in "
                  << duration.count() << "µs" << std::endl;

        return stats;
    }

    std::string detectLanguage() {
        int enScore = 0, frScore = 0;

        for (const auto& [word, count] : wordFreq) {
            if (STOPWORDS_EN.count(word)) enScore += count;
            if (STOPWORDS_FR.count(word)) frScore += count;
        }

        return (frScore > enScore) ? "fr" : "en";
    }

    std::vector<WordFrequency> getTopWords(int n, bool removeStopwords = true) {
        const auto& stopwords = (detectLanguage() == "fr") ? STOPWORDS_FR : STOPWORDS_EN;

        std::vector<WordFrequency> result;

        for (const auto& [word, count] : wordFreq) {
            if (removeStopwords && stopwords.count(word)) continue;
            if (word.length() < 3) continue;

            result.push_back({
                word,
                count,
                static_cast<double>(count) / tokens.size()
            });
        }

        std::sort(result.begin(), result.end(),
            [](const auto& a, const auto& b) { return a.count > b.count; });

        if (result.size() > static_cast<size_t>(n)) {
            result.resize(n);
        }

        return result;
    }

    // N-gram extraction
    std::vector<std::pair<std::string, int>> getNgrams(int n) {
        std::unordered_map<std::string, int> ngrams;

        for (size_t i = 0; i + n <= tokens.size(); i++) {
            std::string ngram;
            for (int j = 0; j < n; j++) {
                if (j > 0) ngram += " ";
                ngram += tokens[i + j];
            }
            ngrams[ngram]++;
        }

        std::vector<std::pair<std::string, int>> result(ngrams.begin(), ngrams.end());
        std::sort(result.begin(), result.end(),
            [](const auto& a, const auto& b) { return a.second > b.second; });

        return result;
    }

    // TF-IDF calculation (simplified, for single document)
    double calculateTF(const std::string& term) {
        std::string lowerTerm = toLower(term);
        auto it = wordFreq.find(lowerTerm);
        if (it == wordFreq.end()) return 0.0;
        return static_cast<double>(it->second) / tokens.size();
    }
};

// ═══════════════════════════════════════════════════════════════════
// JSON OUTPUT
// ═══════════════════════════════════════════════════════════════════

void outputJSON(const TextStats& stats, const std::vector<WordFrequency>& topWords) {
    std::cout << "{\n";
    std::cout << "  \"stats\": {\n";
    std::cout << "    \"char_count\": " << stats.charCount << ",\n";
    std::cout << "    \"word_count\": " << stats.wordCount << ",\n";
    std::cout << "    \"sentence_count\": " << stats.sentenceCount << ",\n";
    std::cout << "    \"unique_words\": " << stats.uniqueWords << ",\n";
    std::cout << "    \"avg_word_length\": " << stats.avgWordLength << ",\n";
    std::cout << "    \"lexical_diversity\": " << stats.lexicalDiversity << ",\n";
    std::cout << "    \"language\": \"" << stats.detectedLanguage << "\"\n";
    std::cout << "  },\n";
    std::cout << "  \"keywords\": [\n";

    for (size_t i = 0; i < topWords.size(); i++) {
        std::cout << "    {\"word\": \"" << topWords[i].word
                  << "\", \"count\": " << topWords[i].count
                  << ", \"tf\": " << topWords[i].tf << "}";
        if (i < topWords.size() - 1) std::cout << ",";
        std::cout << "\n";
    }

    std::cout << "  ]\n";
    std::cout << "}\n";
}

// ═══════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════

void printBanner() {
    std::cerr << R"(
╔═══════════════════════════════════════════════════════════╗
║     HybridCore Text Processor - C++ High Performance      ║
║     Compiled with -O3 for maximum speed                   ║
╚═══════════════════════════════════════════════════════════╝
)" << std::endl;
}

int main(int argc, char* argv[]) {
    printBanner();

    std::string text;

    if (argc > 1) {
        // Read from file
        std::ifstream file(argv[1]);
        if (!file) {
            std::cerr << "Error: Cannot open file " << argv[1] << std::endl;
            return 1;
        }
        std::stringstream buffer;
        buffer << file.rdbuf();
        text = buffer.str();
    } else {
        // Read from stdin
        std::stringstream buffer;
        buffer << std::cin.rdbuf();
        text = buffer.str();
    }

    if (text.empty()) {
        std::cerr << "Error: No input text" << std::endl;
        return 1;
    }

    TextProcessor processor;
    TextStats stats = processor.analyze(text);
    auto topWords = processor.getTopWords(20);

    outputJSON(stats, topWords);

    return 0;
}
