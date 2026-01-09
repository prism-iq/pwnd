package db

import (
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/jmoiron/sqlx"
	_ "github.com/lib/pq"
)

var DB *sqlx.DB

type Document struct {
	ID        int       `db:"id" json:"id"`
	DocID     string    `db:"doc_id" json:"doc_id"`
	Filename  string    `db:"filename" json:"filename"`
	Title     string    `db:"title" json:"title"`
	Content   string    `db:"content" json:"content"`
	WordCount int       `db:"word_count" json:"word_count"`
	CreatedAt time.Time `db:"created_at" json:"created_at"`
}

type SearchResult struct {
	Document
	Rank    float64 `db:"rank" json:"rank"`
	Excerpt string  `db:"excerpt" json:"excerpt"`
}

type Entity struct {
	ID       int     `db:"id" json:"id"`
	Name     string  `db:"name" json:"name"`
	Type     string  `db:"type" json:"type"`
	Confidence float64 `db:"confidence" json:"confidence"`
}

type Edge struct {
	ID           int     `db:"id" json:"id"`
	FromEntityID int     `db:"from_entity_id" json:"from_entity_id"`
	ToEntityID   int     `db:"to_entity_id" json:"to_entity_id"`
	Relationship string  `db:"relationship" json:"relationship"`
	Weight       float64 `db:"weight" json:"weight"`
}

func Connect(host string, port int, user, password, dbname string) error {
	dsn := fmt.Sprintf("host=%s port=%d user=%s password=%s dbname=%s sslmode=disable",
		host, port, user, password, dbname)

	var err error
	DB, err = sqlx.Connect("postgres", dsn)
	if err != nil {
		return fmt.Errorf("db connect: %w", err)
	}

	DB.SetMaxOpenConns(25)
	DB.SetMaxIdleConns(5)
	DB.SetConnMaxLifetime(5 * time.Minute)

	log.Println("[DB] Connected to PostgreSQL")
	return nil
}

func Search(query string, limit int) ([]SearchResult, error) {
	if limit <= 0 {
		limit = 5
	}

	// Convert query to OR-based search: "explain Go goroutines" -> "explain OR Go OR goroutines"
	orQuery := strings.Join(strings.Fields(query), " OR ")

	sql := `
		SELECT d.id, d.doc_id, d.filename, d.title, d.content, d.word_count, d.created_at,
			ts_rank(d.search_vector, websearch_to_tsquery('english', $1)) as rank,
			ts_headline('english', d.content, websearch_to_tsquery('english', $1),
				'MaxWords=60, MinWords=30, StartSel=**, StopSel=**') as excerpt
		FROM documents d
		WHERE d.search_vector @@ websearch_to_tsquery('english', $1)
		ORDER BY rank DESC
		LIMIT $2`

	var results []SearchResult
	err := DB.Select(&results, sql, orQuery, limit)
	return results, err
}

func GetDocument(id int) (*Document, error) {
	var doc Document
	err := DB.Get(&doc, "SELECT id, doc_id, filename, title, content, word_count, created_at FROM documents WHERE id = $1", id)
	if err != nil {
		return nil, err
	}
	return &doc, nil
}

func ListDocuments() ([]Document, error) {
	var docs []Document
	err := DB.Select(&docs, "SELECT id, doc_id, filename, title, word_count, created_at FROM documents ORDER BY id")
	return docs, err
}

func InsertDocument(filename, title, content string) (*Document, error) {
	sql := `INSERT INTO documents (filename, title, content, word_count, char_count)
		VALUES ($1, $2, $3, $4, $5) RETURNING id, doc_id, filename, title, content, word_count, created_at`

	words := len(splitWords(content))
	chars := len(content)

	var doc Document
	err := DB.Get(&doc, sql, filename, title, content, words, chars)
	return &doc, err
}

func GetStats() map[string]interface{} {
	stats := make(map[string]interface{})

	var docCount int
	DB.Get(&docCount, "SELECT COUNT(*) FROM documents")
	stats["documents"] = docCount

	var entityCount int
	DB.Get(&entityCount, "SELECT COUNT(*) FROM entities")
	stats["entities"] = entityCount

	var edgeCount int
	DB.Get(&edgeCount, "SELECT COUNT(*) FROM edges")
	stats["edges"] = edgeCount

	return stats
}

func splitWords(s string) []string {
	var words []string
	word := ""
	for _, r := range s {
		if r == ' ' || r == '\n' || r == '\t' {
			if word != "" {
				words = append(words, word)
				word = ""
			}
		} else {
			word += string(r)
		}
	}
	if word != "" {
		words = append(words, word)
	}
	return words
}
