package main

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	_ "github.com/lib/pq"
)

var db *sql.DB

type SearchResult struct {
	ID       int     `json:"id"`
	Name     string  `json:"name"`
	Snippet  string  `json:"snippet"`
	Rank     float64 `json:"rank"`
	Type     string  `json:"type"`
}

type HealthResponse struct {
	Status    string `json:"status"`
	Timestamp string `json:"timestamp"`
	DB        string `json:"db"`
}

func main() {
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		log.Fatal("DATABASE_URL required")
	}

	var err error
	db, err = sql.Open("postgres", dbURL)
	if err != nil {
		log.Fatal(err)
	}
	db.SetMaxOpenConns(20)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(5 * time.Minute)

	if err = db.Ping(); err != nil {
		log.Fatal("DB ping failed:", err)
	}
	log.Println("Connected to PostgreSQL")

	http.HandleFunc("/health", healthHandler)
	http.HandleFunc("/search", searchHandler)
	http.HandleFunc("/search/fast", fastSearchHandler)

	port := os.Getenv("GO_PORT")
	if port == "" {
		port = "8003"
	}
	log.Printf("Go search service on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(HealthResponse{
		Status:    "ok",
		Timestamp: time.Now().Format(time.RFC3339),
		DB:        "connected",
	})
}

func searchHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	if q == "" {
		http.Error(w, `{"error":"q required"}`, 400)
		return
	}

	start := time.Now()
	rows, err := db.Query(`
		SELECT doc_id, subject, 
			ts_headline('english', COALESCE(body_text,''), plainto_tsquery('english', $1), 
				'StartSel=<b>, StopSel=</b>, MaxWords=30') as snippet,
			ts_rank(tsv, plainto_tsquery('english', $1)) as rank
		FROM emails
		WHERE tsv @@ plainto_tsquery('english', $1)
		ORDER BY rank DESC
		LIMIT 20
	`, q)
	if err != nil {
		http.Error(w, fmt.Sprintf(`{"error":"%s"}`, err), 500)
		return
	}
	defer rows.Close()

	var results []SearchResult
	for rows.Next() {
		var r SearchResult
		r.Type = "email"
		if err := rows.Scan(&r.ID, &r.Name, &r.Snippet, &r.Rank); err != nil {
			continue
		}
		results = append(results, r)
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Search-Time", fmt.Sprintf("%dms", time.Since(start).Milliseconds()))
	json.NewEncoder(w).Encode(results)
}

func fastSearchHandler(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	if q == "" {
		http.Error(w, `{"error":"q required"}`, 400)
		return
	}

	terms := strings.Fields(q)
	start := time.Now()

	// Parallel search on multiple terms
	resultChan := make(chan []SearchResult, len(terms))
	for _, term := range terms[:min(4, len(terms))] {
		go func(t string) {
			rows, err := db.Query(`
				SELECT doc_id, subject, '' as snippet,
					ts_rank(tsv, plainto_tsquery('english', $1)) as rank
				FROM emails
				WHERE tsv @@ plainto_tsquery('english', $1)
				ORDER BY rank DESC LIMIT 15
			`, t)
			if err != nil {
				resultChan <- nil
				return
			}
			defer rows.Close()
			var res []SearchResult
			for rows.Next() {
				var r SearchResult
				r.Type = "email"
				rows.Scan(&r.ID, &r.Name, &r.Snippet, &r.Rank)
				res = append(res, r)
			}
			resultChan <- res
		}(term)
	}

	// Collect and dedupe
	seen := make(map[int]bool)
	var results []SearchResult
	for i := 0; i < min(4, len(terms)); i++ {
		res := <-resultChan
		for _, r := range res {
			if !seen[r.ID] {
				seen[r.ID] = true
				results = append(results, r)
			}
		}
	}

	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Search-Time", fmt.Sprintf("%dms", time.Since(start).Milliseconds()))
	json.NewEncoder(w).Encode(results)
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
