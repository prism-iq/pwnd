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

	// Try LLM analysis, but always have a good fallback
	resp, err := e.llmClient.Analyze(query, context)
	if err != nil || resp == nil || resp.Analysis == "" {
		if err != nil {
			log.Printf("[RAG] LLM analyze error: %v", err)
		}
		// Generate smart answer from sources
		return &RAGResult{
			Answer:           buildSmartAnswer(query, results),
			Sources:          sources,
			SuggestedQueries: generateSuggestions(query, results),
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

func buildSmartAnswer(query string, results []db.SearchResult) string {
	if len(results) == 0 {
		return "Aucun résultat trouvé pour cette recherche."
	}

	queryLower := strings.ToLower(query)
	var answer strings.Builder

	// Analyze query intent
	isWhoQuery := strings.Contains(queryLower, "who") || strings.Contains(queryLower, "qui")
	isWhatQuery := strings.Contains(queryLower, "what") || strings.Contains(queryLower, "quoi") || strings.Contains(queryLower, "quel")
	isConnectionQuery := strings.Contains(queryLower, "connection") || strings.Contains(queryLower, "associate") || strings.Contains(queryLower, "lien")

	// Build contextual intro
	topResult := results[0]
	if isWhoQuery || isConnectionQuery {
		answer.WriteString(fmt.Sprintf("Based on the documents, here's what I found about **%s**:\n\n", extractMainSubject(query)))
	} else if isWhatQuery {
		answer.WriteString(fmt.Sprintf("Here's the relevant information from %d source(s):\n\n", len(results)))
	} else {
		answer.WriteString(fmt.Sprintf("Found %d relevant document(s). Top result: **%s**\n\n", len(results), topResult.Title))
	}

	// Extract key facts from top results
	for i, r := range results {
		if i >= 3 {
			break
		}

		// Extract meaningful excerpts
		excerpt := cleanExcerpt(r.Excerpt)
		if len(excerpt) > 300 {
			excerpt = excerpt[:300] + "..."
		}

		answer.WriteString(fmt.Sprintf("**[%d] %s**\n", i+1, r.Title))
		answer.WriteString(fmt.Sprintf("%s\n\n", excerpt))
	}

	if len(results) > 3 {
		answer.WriteString(fmt.Sprintf("_...and %d more sources available._\n", len(results)-3))
	}

	return answer.String()
}

func extractMainSubject(query string) string {
	// Extract the main subject from the query
	words := strings.Fields(query)
	var subjects []string

	skipWords := map[string]bool{
		"who": true, "what": true, "where": true, "when": true, "how": true,
		"is": true, "are": true, "was": true, "were": true, "the": true,
		"a": true, "an": true, "of": true, "to": true, "in": true,
		"qui": true, "quoi": true, "est": true, "sont": true, "le": true, "la": true,
	}

	for _, w := range words {
		wLower := strings.ToLower(w)
		if !skipWords[wLower] && len(w) > 2 {
			// Capitalize proper nouns
			subjects = append(subjects, strings.Title(strings.ToLower(w)))
		}
	}

	if len(subjects) == 0 {
		return "this topic"
	}
	if len(subjects) > 3 {
		subjects = subjects[:3]
	}
	return strings.Join(subjects, " ")
}

func cleanExcerpt(excerpt string) string {
	// Remove markdown bold markers used for highlighting
	excerpt = strings.ReplaceAll(excerpt, "**", "")
	// Clean up extra whitespace
	excerpt = strings.Join(strings.Fields(excerpt), " ")
	return excerpt
}

func generateSuggestions(query string, results []db.SearchResult) []string {
	var suggestions []string

	if len(results) == 0 {
		return suggestions
	}

	// Extract entities from results to suggest follow-up queries
	entities := make(map[string]bool)

	for _, r := range results {
		titleWords := strings.Fields(r.Title)
		for _, w := range titleWords {
			if len(w) > 3 && w[0] >= 'A' && w[0] <= 'Z' {
				entities[w] = true
			}
		}
	}

	// Generate suggestions based on found entities
	for entity := range entities {
		if len(suggestions) >= 3 {
			break
		}
		if !strings.Contains(strings.ToLower(query), strings.ToLower(entity)) {
			suggestions = append(suggestions, fmt.Sprintf("What is %s's connection to this case?", entity))
		}
	}

	// Add generic follow-ups if needed
	genericFollowups := []string{
		"What evidence exists?",
		"Who else was involved?",
		"What are the key dates?",
	}

	for _, g := range genericFollowups {
		if len(suggestions) >= 3 {
			break
		}
		suggestions = append(suggestions, g)
	}

	return suggestions
}

func truncate(s string, maxLen int) string {
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen-3] + "..."
}
