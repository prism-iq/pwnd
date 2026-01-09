package rag

import (
	"fmt"
	"log"
	"strings"

	"hybridcore/internal/db"
	"hybridcore/internal/llm"
)

type Engine struct {
	llmClient *llm.Client
}

type RAGResult struct {
	Answer           string   `json:"answer"`
	Sources          []Source `json:"sources"`
	SuggestedQueries []string `json:"suggested_queries,omitempty"`
}

type Source struct {
	DocID   string  `json:"doc_id"`
	Title   string  `json:"title"`
	Excerpt string  `json:"excerpt"`
	Rank    float64 `json:"rank"`
}

func NewEngine(llmClient *llm.Client) *Engine {
	return &Engine{llmClient: llmClient}
}

func (e *Engine) Query(query string, limit int) (*RAGResult, error) {
	if limit <= 0 {
		limit = 5
	}

	// Search documents using PostgreSQL FTS
	results, err := db.Search(query, limit)
	if err != nil {
		log.Printf("[RAG] Search error: %v", err)
		return nil, fmt.Errorf("search: %w", err)
	}

	// Build context from search results
	var contextParts []string
	var sources []Source

	for i, r := range results {
		contextParts = append(contextParts, fmt.Sprintf(
			"[Document #%d: %s]\n%s\n",
			i+1, r.Title, r.Excerpt,
		))

		sources = append(sources, Source{
			DocID:   r.DocID,
			Title:   r.Title,
			Excerpt: truncate(r.Excerpt, 200),
			Rank:    r.Rank,
		})
	}

	if len(results) == 0 {
		return &RAGResult{
			Answer:  "Je n'ai pas trouvé d'informations pertinentes dans les documents.",
			Sources: sources,
		}, nil
	}

	context := strings.Join(contextParts, "\n---\n")

	// Analyze with LLM
	resp, err := e.llmClient.Analyze(query, context)
	if err != nil {
		log.Printf("[RAG] LLM analyze error: %v", err)
		// Fallback to basic response
		return &RAGResult{
			Answer:  buildBasicAnswer(query, results),
			Sources: sources,
		}, nil
	}

	return &RAGResult{
		Answer:           resp.Analysis,
		Sources:          sources,
		SuggestedQueries: resp.SuggestedQueries,
	}, nil
}

func (e *Engine) GetStats() map[string]interface{} {
	stats := db.GetStats()

	// Add LLM health
	if health, err := e.llmClient.Health(); err == nil {
		stats["llm_status"] = health.Status
		stats["llm_model"] = health.Model
		stats["llm_ready"] = health.Ready
	} else {
		stats["llm_status"] = "offline"
		stats["llm_error"] = err.Error()
	}

	return stats
}

func buildBasicAnswer(query string, results []db.SearchResult) string {
	if len(results) == 0 {
		return "Aucun résultat trouvé."
	}

	var parts []string
	parts = append(parts, fmt.Sprintf("J'ai trouvé %d résultat(s) pertinent(s):\n", len(results)))

	for i, r := range results {
		parts = append(parts, fmt.Sprintf(
			"%d. **%s** [#%s]\n   %s\n",
			i+1, r.Title, r.DocID, truncate(r.Excerpt, 150),
		))
	}

	return strings.Join(parts, "\n")
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}
