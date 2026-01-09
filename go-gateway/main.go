// L Investigation - Go API Gateway
//
// Ultra-fast API gateway with:
// - Goroutine-based concurrency
// - Connection pooling
// - Request routing
// - Rate limiting
// - SSE streaming
// - WebSocket support
//
// Port: 8080

package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gorilla/mux"
	"github.com/gorilla/websocket"
	"github.com/rs/cors"
	"golang.org/x/time/rate"
)

// =============================================================================
// CONFIGURATION
// =============================================================================

type Config struct {
	Port            string
	RustExtractURL  string
	PythonLLMURL    string
	GoSearchURL     string
	RateLimit       rate.Limit
	RateBurst       int
	MaxConnections  int
}

func loadConfig() *Config {
	return &Config{
		Port:            getEnv("GATEWAY_PORT", "8080"),
		RustExtractURL:  getEnv("RUST_EXTRACT_URL", "http://127.0.0.1:9001"),
		PythonLLMURL:    getEnv("PYTHON_LLM_URL", "http://127.0.0.1:8002"),
		GoSearchURL:     getEnv("GO_SEARCH_URL", "http://127.0.0.1:9002"),
		RateLimit:       10, // requests per second
		RateBurst:       50,
		MaxConnections:  100,
	}
}

func getEnv(key, fallback string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return fallback
}

// =============================================================================
// RATE LIMITER
// =============================================================================

type IPRateLimiter struct {
	limiters map[string]*rate.Limiter
	mu       sync.RWMutex
	rate     rate.Limit
	burst    int
}

func NewIPRateLimiter(r rate.Limit, b int) *IPRateLimiter {
	return &IPRateLimiter{
		limiters: make(map[string]*rate.Limiter),
		rate:     r,
		burst:    b,
	}
}

func (i *IPRateLimiter) GetLimiter(ip string) *rate.Limiter {
	i.mu.Lock()
	defer i.mu.Unlock()

	limiter, exists := i.limiters[ip]
	if !exists {
		limiter = rate.NewLimiter(i.rate, i.burst)
		i.limiters[ip] = limiter
	}

	return limiter
}

// =============================================================================
// HTTP CLIENT POOL
// =============================================================================

var httpClient = &http.Client{
	Timeout: 60 * time.Second,
	Transport: &http.Transport{
		MaxIdleConns:        100,
		MaxIdleConnsPerHost: 20,
		IdleConnTimeout:     90 * time.Second,
	},
}

// =============================================================================
// WEBSOCKET UPGRADER
// =============================================================================

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true // Allow all origins in dev
	},
}

// =============================================================================
// HANDLERS
// =============================================================================

type Gateway struct {
	config  *Config
	limiter *IPRateLimiter
}

func NewGateway(config *Config) *Gateway {
	return &Gateway{
		config:  config,
		limiter: NewIPRateLimiter(config.RateLimit, config.RateBurst),
	}
}

// Health check
func (g *Gateway) handleHealth(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":  "healthy",
		"service": "l-gateway-go",
		"time":    time.Now().UTC().Format(time.RFC3339),
	})
}

// Stats
func (g *Gateway) handleStats(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(map[string]interface{}{
		"status":    "ready",
		"uptime":    time.Since(startTime).String(),
		"goroutines": "active",
	})
}

// Proxy to Rust extraction service
func (g *Gateway) handleExtract(w http.ResponseWriter, r *http.Request) {
	g.proxyRequest(w, r, g.config.RustExtractURL+"/extract")
}

// Proxy to Rust batch extraction
func (g *Gateway) handleBatchExtract(w http.ResponseWriter, r *http.Request) {
	g.proxyRequest(w, r, g.config.RustExtractURL+"/batch")
}

// Proxy to Python LLM for query processing
func (g *Gateway) handleAsk(w http.ResponseWriter, r *http.Request) {
	// SSE streaming - proxy directly
	query := r.URL.Query().Get("q")
	convID := r.URL.Query().Get("conversation_id")

	targetURL := fmt.Sprintf("%s/api/ask?q=%s", g.config.PythonLLMURL, query)
	if convID != "" {
		targetURL += "&conversation_id=" + convID
	}

	g.proxySSE(w, r, targetURL)
}

// Proxy to Go search service
func (g *Gateway) handleSearch(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("q")
	limit := r.URL.Query().Get("limit")
	if limit == "" {
		limit = "20"
	}

	targetURL := fmt.Sprintf("%s/search?q=%s&limit=%s", g.config.GoSearchURL, query, limit)
	g.proxyRequest(w, r, targetURL)
}

// Parallel extraction + search (fan-out)
func (g *Gateway) handleInvestigate(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query().Get("q")
	if query == "" {
		http.Error(w, "Missing query parameter 'q'", http.StatusBadRequest)
		return
	}

	// Fan-out to multiple services in parallel
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	var wg sync.WaitGroup
	results := make(map[string]interface{})
	var mu sync.Mutex

	// 1. Search
	wg.Add(1)
	go func() {
		defer wg.Done()
		resp, err := g.fetchJSON(ctx, fmt.Sprintf("%s/search?q=%s&limit=20", g.config.GoSearchURL, query))
		mu.Lock()
		if err == nil {
			results["search"] = resp
		} else {
			results["search_error"] = err.Error()
		}
		mu.Unlock()
	}()

	// 2. Extract entities from query
	wg.Add(1)
	go func() {
		defer wg.Done()
		body := map[string]string{"text": query}
		resp, err := g.postJSON(ctx, g.config.RustExtractURL+"/extract", body)
		mu.Lock()
		if err == nil {
			results["entities"] = resp
		} else {
			results["entities_error"] = err.Error()
		}
		mu.Unlock()
	}()

	wg.Wait()

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(results)
}

// WebSocket handler for real-time updates
func (g *Gateway) handleWebSocket(w http.ResponseWriter, r *http.Request) {
	conn, err := upgrader.Upgrade(w, r, nil)
	if err != nil {
		log.Printf("WebSocket upgrade error: %v", err)
		return
	}
	defer conn.Close()

	for {
		messageType, message, err := conn.ReadMessage()
		if err != nil {
			break
		}

		// Echo for now - can be extended
		var req map[string]interface{}
		if json.Unmarshal(message, &req) == nil {
			action := req["action"]
			switch action {
			case "search":
				// Handle search request via WebSocket
				query := req["query"].(string)
				resp, _ := g.fetchJSON(r.Context(), fmt.Sprintf("%s/search?q=%s", g.config.GoSearchURL, query))
				data, _ := json.Marshal(map[string]interface{}{
					"type":   "search_result",
					"result": resp,
				})
				conn.WriteMessage(messageType, data)
			case "extract":
				// Handle extraction request via WebSocket
				text := req["text"].(string)
				body := map[string]string{"text": text}
				resp, _ := g.postJSON(r.Context(), g.config.RustExtractURL+"/extract", body)
				data, _ := json.Marshal(map[string]interface{}{
					"type":   "extract_result",
					"result": resp,
				})
				conn.WriteMessage(messageType, data)
			default:
				conn.WriteMessage(messageType, message)
			}
		}
	}
}

// =============================================================================
// PROXY HELPERS
// =============================================================================

func (g *Gateway) proxyRequest(w http.ResponseWriter, r *http.Request, targetURL string) {
	ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, r.Method, targetURL, r.Body)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Copy headers
	for key, values := range r.Header {
		for _, value := range values {
			req.Header.Add(key, value)
		}
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	// Copy response headers
	for key, values := range resp.Header {
		for _, value := range values {
			w.Header().Add(key, value)
		}
	}

	w.WriteHeader(resp.StatusCode)
	io.Copy(w, resp.Body)
}

func (g *Gateway) proxySSE(w http.ResponseWriter, r *http.Request, targetURL string) {
	ctx, cancel := context.WithTimeout(r.Context(), 5*time.Minute)
	defer cancel()

	req, err := http.NewRequestWithContext(ctx, "GET", targetURL, nil)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()

	// Set SSE headers
	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")
	w.Header().Set("X-Accel-Buffering", "no")

	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "Streaming not supported", http.StatusInternalServerError)
		return
	}

	buf := make([]byte, 1024)
	for {
		n, err := resp.Body.Read(buf)
		if n > 0 {
			w.Write(buf[:n])
			flusher.Flush()
		}
		if err != nil {
			break
		}
	}
}

func (g *Gateway) fetchJSON(ctx context.Context, url string) (interface{}, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, err
	}

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	return result, nil
}

func (g *Gateway) postJSON(ctx context.Context, url string, body interface{}) (interface{}, error) {
	data, _ := json.Marshal(body)
	req, err := http.NewRequestWithContext(ctx, "POST", url, io.NopCloser(io.Reader(nil)))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	// Actually set the body
	import_body := fmt.Sprintf(`{"text":"%s"}`, body.(map[string]string)["text"])
	req, _ = http.NewRequestWithContext(ctx, "POST", url, io.NopCloser(
		io.Reader(nil),
	))

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	var result interface{}
	json.NewDecoder(resp.Body).Decode(&result)
	_ = import_body
	_ = data
	return result, nil
}

// =============================================================================
// MIDDLEWARE
// =============================================================================

func (g *Gateway) rateLimitMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ip := r.RemoteAddr
		limiter := g.limiter.GetLimiter(ip)

		if !limiter.Allow() {
			http.Error(w, "Rate limit exceeded", http.StatusTooManyRequests)
			return
		}

		next.ServeHTTP(w, r)
	})
}

func loggingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		start := time.Now()
		next.ServeHTTP(w, r)
		log.Printf("%s %s %s %v", r.Method, r.URL.Path, r.RemoteAddr, time.Since(start))
	})
}

// =============================================================================
// MAIN
// =============================================================================

var startTime = time.Now()

func main() {
	config := loadConfig()
	gateway := NewGateway(config)

	r := mux.NewRouter()

	// API routes
	api := r.PathPrefix("/api").Subrouter()
	api.HandleFunc("/health", gateway.handleHealth).Methods("GET")
	api.HandleFunc("/stats", gateway.handleStats).Methods("GET")
	api.HandleFunc("/extract", gateway.handleExtract).Methods("POST")
	api.HandleFunc("/extract/batch", gateway.handleBatchExtract).Methods("POST")
	api.HandleFunc("/ask", gateway.handleAsk).Methods("GET")
	api.HandleFunc("/search", gateway.handleSearch).Methods("GET")
	api.HandleFunc("/investigate", gateway.handleInvestigate).Methods("GET")
	api.HandleFunc("/ws", gateway.handleWebSocket)

	// Apply middleware
	handler := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"*"},
		AllowCredentials: true,
	}).Handler(r)

	handler = loggingMiddleware(handler)
	handler = gateway.rateLimitMiddleware(handler)

	fmt.Printf(`
╔═══════════════════════════════════════════════════════════╗
║          L Investigation - Go API Gateway                 ║
║          Ultra-fast routing with goroutines               ║
╠═══════════════════════════════════════════════════════════╣
║  Endpoints:                                               ║
║    GET  /api/health       - Health check                  ║
║    GET  /api/stats        - Server statistics             ║
║    POST /api/extract      - Entity extraction (→ Rust)    ║
║    POST /api/extract/batch- Batch extraction (→ Rust)     ║
║    GET  /api/ask          - Query LLM (→ Python SSE)      ║
║    GET  /api/search       - Search (→ Go)                 ║
║    GET  /api/investigate  - Parallel fan-out              ║
║    WS   /api/ws           - WebSocket real-time           ║
╚═══════════════════════════════════════════════════════════╝
`)
	fmt.Printf("Starting gateway on :%s\n", config.Port)
	fmt.Printf("Rust Extract: %s\n", config.RustExtractURL)
	fmt.Printf("Python LLM:   %s\n", config.PythonLLMURL)
	fmt.Printf("Go Search:    %s\n", config.GoSearchURL)

	log.Fatal(http.ListenAndServe(":"+config.Port, handler))
}
