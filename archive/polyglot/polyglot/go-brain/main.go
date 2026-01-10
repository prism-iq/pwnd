// L Investigation - Go Gateway (BRAIN)
//
// The brain coordinates all organs:
// - Routes requests to appropriate services
// - Makes strategic decisions
// - Manages rate limiting & security
// - Handles concurrent operations with goroutines

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"sync/atomic"
	"time"

	"github.com/gorilla/mux"
	"golang.org/x/time/rate"
)

// =============================================================================
// ORGAN REGISTRY
// =============================================================================

type Organ struct {
	Name    string
	URL     string
	Healthy bool
	Latency time.Duration
}

var organs = map[string]*Organ{
	"lungs": {Name: "lungs", URL: "http://127.0.0.1:3000"},  // Node.js
	"cells": {Name: "cells", URL: "http://127.0.0.1:9001"},  // Rust
	"veins": {Name: "veins", URL: "http://127.0.0.1:8000"},  // Python
	"blood": {Name: "blood", URL: "http://127.0.0.1:9003"},  // C++
}

var organMu sync.RWMutex

// =============================================================================
// BRAIN METRICS (neural activity)
// =============================================================================

type BrainMetrics struct {
	Thoughts    atomic.Int64 // requests processed
	Decisions   atomic.Int64 // successful decisions
	Errors      atomic.Int64 // errors
	NeuralPaths atomic.Int64 // concurrent goroutines
	StartTime   time.Time
}

var metrics = BrainMetrics{StartTime: time.Now()}

// =============================================================================
// RATE LIMITER (impulse control)
// =============================================================================

var limiter = rate.NewLimiter(rate.Limit(100), 200) // 100 req/s, burst 200

// =============================================================================
// STRATEGIC ANALYSIS
// =============================================================================

type AnalysisRequest struct {
	Query  string `json:"query"`
	Domain string `json:"domain,omitempty"`
}

type Strategy struct {
	Priority    string   `json:"priority"`
	SearchTerms []string `json:"search_terms"`
	EntityTypes []string `json:"entity_types"`
	Confidence  float64  `json:"confidence"`
}

func analyzeQuery(query string) Strategy {
	// Brain decides strategy based on query content
	strategy := Strategy{
		Priority:    "normal",
		SearchTerms: []string{},
		EntityTypes: []string{"person", "organization", "money", "date"},
		Confidence:  0.8,
	}

	// High priority patterns
	highPriorityKeywords := []string{"fraud", "criminal", "urgent", "breaking", "money laundering"}
	for _, kw := range highPriorityKeywords {
		if containsIgnoreCase(query, kw) {
			strategy.Priority = "high"
			strategy.Confidence = 0.95
			break
		}
	}

	// Extract search terms (simple tokenization)
	strategy.SearchTerms = tokenize(query)

	return strategy
}

func containsIgnoreCase(s, substr string) bool {
	return bytes.Contains(bytes.ToLower([]byte(s)), bytes.ToLower([]byte(substr)))
}

func tokenize(s string) []string {
	var tokens []string
	var current []byte
	for _, c := range []byte(s) {
		if (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') {
			current = append(current, c)
		} else if len(current) > 2 {
			tokens = append(tokens, string(current))
			current = nil
		} else {
			current = nil
		}
	}
	if len(current) > 2 {
		tokens = append(tokens, string(current))
	}
	return tokens
}

// =============================================================================
// ORGAN COMMUNICATION
// =============================================================================

func callOrgan(ctx context.Context, organName, path string, data interface{}) (map[string]interface{}, error) {
	organMu.RLock()
	organ, ok := organs[organName]
	organMu.RUnlock()

	if !ok {
		return nil, fmt.Errorf("unknown organ: %s", organName)
	}

	body, _ := json.Marshal(data)
	req, err := http.NewRequestWithContext(ctx, "POST", organ.URL+path, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	start := time.Now()
	resp, err := http.DefaultClient.Do(req)
	latency := time.Since(start)

	organMu.Lock()
	organ.Latency = latency
	organMu.Unlock()

	if err != nil {
		organMu.Lock()
		organ.Healthy = false
		organMu.Unlock()
		return nil, err
	}
	defer resp.Body.Close()

	organMu.Lock()
	organ.Healthy = resp.StatusCode == 200
	organMu.Unlock()

	respBody, _ := io.ReadAll(resp.Body)
	var result map[string]interface{}
	json.Unmarshal(respBody, &result)

	return result, nil
}

// =============================================================================
// HTTP HANDLERS
// =============================================================================

func analyzeHandler(w http.ResponseWriter, r *http.Request) {
	if !limiter.Allow() {
		http.Error(w, "rate limited", http.StatusTooManyRequests)
		return
	}

	metrics.Thoughts.Add(1)

	var req AnalysisRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		metrics.Errors.Add(1)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	strategy := analyzeQuery(req.Query)
	metrics.Decisions.Add(1)

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(strategy)
}

func investigateHandler(w http.ResponseWriter, r *http.Request) {
	if !limiter.Allow() {
		http.Error(w, "rate limited", http.StatusTooManyRequests)
		return
	}

	metrics.Thoughts.Add(1)
	ctx := r.Context()

	var req struct {
		Query     string `json:"query"`
		Domain    string `json:"domain,omitempty"`
		SessionID string `json:"sessionId,omitempty"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		metrics.Errors.Add(1)
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	// Phase 1: Analyze and create strategy
	strategy := analyzeQuery(req.Query)

	// Phase 2: Parallel organ calls with goroutines (neural pathways)
	var wg sync.WaitGroup
	var extractResult, searchResult map[string]interface{}
	var extractErr, searchErr error

	// Cells (Rust) - entity extraction
	wg.Add(1)
	metrics.NeuralPaths.Add(1)
	go func() {
		defer wg.Done()
		defer metrics.NeuralPaths.Add(-1)
		extractResult, extractErr = callOrgan(ctx, "cells", "/extract", map[string]string{"text": req.Query})
	}()

	// Blood (C++) - search
	wg.Add(1)
	metrics.NeuralPaths.Add(1)
	go func() {
		defer wg.Done()
		defer metrics.NeuralPaths.Add(-1)
		searchResult, searchErr = callOrgan(ctx, "blood", "/search", map[string]interface{}{
			"query": req.Query,
			"limit": 20,
		})
	}()

	wg.Wait()

	// Phase 3: Synthesize with veins (Python/LLM)
	synthesisInput := map[string]interface{}{
		"query":    req.Query,
		"strategy": strategy,
		"entities": extractResult,
		"search":   searchResult,
	}

	var synthesisResult map[string]interface{}
	if extractErr == nil && searchErr == nil {
		synthesisResult, _ = callOrgan(ctx, "veins", "/synthesize", synthesisInput)
	}

	metrics.Decisions.Add(1)

	// Return combined result
	response := map[string]interface{}{
		"success":   true,
		"sessionId": req.SessionID,
		"strategy":  strategy,
		"entities":  extractResult,
		"search":    searchResult,
		"synthesis": synthesisResult,
		"errors": map[string]string{
			"extract": errStr(extractErr),
			"search":  errStr(searchErr),
		},
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

func errStr(err error) string {
	if err != nil {
		return err.Error()
	}
	return ""
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	metrics.Thoughts.Add(1)

	// Check all organs in parallel
	organHealth := make(map[string]map[string]interface{})
	var wg sync.WaitGroup
	var mu sync.Mutex

	for name, organ := range organs {
		wg.Add(1)
		go func(n string, o *Organ) {
			defer wg.Done()

			ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
			defer cancel()

			start := time.Now()
			req, _ := http.NewRequestWithContext(ctx, "GET", o.URL+"/health", nil)
			resp, err := http.DefaultClient.Do(req)
			latency := time.Since(start)

			status := "offline"
			if err == nil && resp.StatusCode == 200 {
				status = "healthy"
				resp.Body.Close()
			}

			mu.Lock()
			organHealth[n] = map[string]interface{}{
				"status":  status,
				"latency": latency.Milliseconds(),
			}
			mu.Unlock()
		}(name, organ)
	}
	wg.Wait()

	response := map[string]interface{}{
		"status": "thinking",
		"uptime": time.Since(metrics.StartTime).Seconds(),
		"metrics": map[string]int64{
			"thoughts":     metrics.Thoughts.Load(),
			"decisions":    metrics.Decisions.Load(),
			"errors":       metrics.Errors.Load(),
			"neural_paths": metrics.NeuralPaths.Load(),
		},
		"organs": organHealth,
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(response)
}

// =============================================================================
// MAIN
// =============================================================================

func main() {
	r := mux.NewRouter()

	// API routes
	r.HandleFunc("/analyze", analyzeHandler).Methods("POST")
	r.HandleFunc("/investigate", investigateHandler).Methods("POST")
	r.HandleFunc("/health", healthHandler).Methods("GET")

	// Middleware
	r.Use(func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("X-Brain-Version", "1.0.0")
			next.ServeHTTP(w, r)
		})
	})

	fmt.Println(`
╔═══════════════════════════════════════════════════════════╗
║       L Investigation - Go BRAIN                          ║
║       Decision-making & coordination                      ║
╠═══════════════════════════════════════════════════════════╣
║  Endpoints:                                               ║
║    POST /analyze     - Strategic analysis                ║
║    POST /investigate - Full investigation                ║
║    GET  /health      - Brain & organ health              ║
╠═══════════════════════════════════════════════════════════╣
║  Connected Organs:                                        ║
║    Lungs (Node.js) → http://127.0.0.1:3000               ║
║    Cells (Rust)    → http://127.0.0.1:9001               ║
║    Veins (Python)  → http://127.0.0.1:8000               ║
║    Blood (C++)     → http://127.0.0.1:9003               ║
╚═══════════════════════════════════════════════════════════╝
`)
	port := os.Getenv("BRAIN_PORT")
	if port == "" {
		port = "8085"
	}
	fmt.Printf("Starting brain on :%s\n", port)
	log.Fatal(http.ListenAndServe(":"+port, r))
}
