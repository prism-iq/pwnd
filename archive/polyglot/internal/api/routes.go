package api

import (
	"bufio"
	"encoding/json"
	"fmt"
	"log"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"

	"hybridcore/internal/chat"
	"hybridcore/internal/db"
	"hybridcore/internal/rag"
	"hybridcore/internal/regex"
)

type Server struct {
	app          *fiber.App
	chatManager  *chat.Manager
	ragEngine    *rag.Engine
	regexMatcher *regex.Matcher
}

func NewServer(chatManager *chat.Manager, ragEngine *rag.Engine) *Server {
	app := fiber.New(fiber.Config{
		AppName:      "HybridCore 2.0",
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 120 * time.Second,
	})

	// Middleware
	app.Use(recover.New())
	app.Use(logger.New(logger.Config{
		Format:     "${time} ${status} ${method} ${path} ${latency}\n",
		TimeFormat: "15:04:05",
	}))
	app.Use(cors.New(cors.Config{
		AllowOrigins: "*",
		AllowHeaders: "Origin, Content-Type, Accept",
	}))

	// Security headers
	app.Use(func(c *fiber.Ctx) error {
		c.Set("X-Content-Type-Options", "nosniff")
		c.Set("X-Frame-Options", "DENY")
		c.Set("X-XSS-Protection", "1; mode=block")
		return c.Next()
	})

	s := &Server{
		app:          app,
		chatManager:  chatManager,
		ragEngine:    ragEngine,
		regexMatcher: regex.NewMatcher(),
	}

	s.setupRoutes()
	return s
}

func (s *Server) setupRoutes() {
	// API routes
	api := s.app.Group("/api")

	// Health & stats
	api.Get("/health", s.handleHealth)
	api.Get("/stats", s.handleStats)

	// Chat
	api.Post("/chat", s.handleChat)
	api.Get("/chat/stream", s.handleChatStream) // SSE endpoint

	// Documents
	api.Get("/documents", s.handleListDocuments)
	api.Get("/documents/:id", s.handleGetDocument)
	api.Get("/search", s.handleSearch)

	// Sessions
	api.Get("/sessions", s.handleListSessions)
	api.Get("/sessions/:id", s.handleGetSession)

	// Regex extraction
	api.Post("/regex/extract", s.handleRegexExtract)
	api.Post("/regex/extract/:category", s.handleRegexExtractCategory)
	api.Post("/regex/sensitive", s.handleRegexSensitive)
	api.Post("/regex/redact", s.handleRegexRedact)

	// Static files
	s.app.Static("/", "./static")

	// Fallback to index.html for SPA
	s.app.Get("/*", func(c *fiber.Ctx) error {
		return c.SendFile("./static/index.html")
	})
}

func (s *Server) handleHealth(c *fiber.Ctx) error {
	return c.JSON(fiber.Map{
		"status":    "ok",
		"timestamp": time.Now().Format(time.RFC3339),
		"version":   "2.0.0",
	})
}

func (s *Server) handleStats(c *fiber.Ctx) error {
	stats := s.ragEngine.GetStats()
	return c.JSON(stats)
}

func (s *Server) handleChat(c *fiber.Ctx) error {
	var req chat.ChatRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	if strings.TrimSpace(req.Message) == "" {
		return c.Status(400).JSON(fiber.Map{"error": "Message required"})
	}

	resp, err := s.chatManager.Chat(req)
	if err != nil {
		log.Printf("[API] Chat error: %v", err)
		return c.Status(500).JSON(fiber.Map{"error": "Chat failed"})
	}

	return c.JSON(resp)
}

func (s *Server) handleChatStream(c *fiber.Ctx) error {
	query := c.Query("q")
	sessionID := c.Query("session_id")

	if query == "" {
		return c.Status(400).JSON(fiber.Map{"error": "Query required"})
	}

	// Set SSE headers
	c.Set("Content-Type", "text/event-stream")
	c.Set("Cache-Control", "no-cache")
	c.Set("Connection", "keep-alive")
	c.Set("Transfer-Encoding", "chunked")

	c.Context().SetBodyStreamWriter(func(w *bufio.Writer) {
		// Send initial event
		sendSSE(w, "start", map[string]interface{}{
			"session_id": sessionID,
			"query":      query,
		})

		// Process chat
		req := chat.ChatRequest{
			SessionID: sessionID,
			Message:   query,
		}

		resp, err := s.chatManager.Chat(req)
		if err != nil {
			sendSSE(w, "error", map[string]interface{}{
				"message": "Chat processing failed",
			})
			sendSSE(w, "done", nil)
			return
		}

		// Send response in chunks for SSE effect
		words := strings.Fields(resp.Message)
		chunkSize := 5
		var chunks []string

		for i := 0; i < len(words); i += chunkSize {
			end := i + chunkSize
			if end > len(words) {
				end = len(words)
			}
			chunks = append(chunks, strings.Join(words[i:end], " "))
		}

		for _, chunk := range chunks {
			sendSSE(w, "chunk", map[string]interface{}{
				"text": chunk + " ",
			})
			time.Sleep(50 * time.Millisecond)
		}

		// Send sources
		if len(resp.Sources) > 0 {
			sendSSE(w, "sources", map[string]interface{}{
				"sources": resp.Sources,
			})
		}

		// Send suggestions
		if len(resp.SuggestedQueries) > 0 {
			sendSSE(w, "suggestions", map[string]interface{}{
				"queries": resp.SuggestedQueries,
			})
		}

		// Done
		sendSSE(w, "done", map[string]interface{}{
			"session_id": resp.SessionID,
		})
	})

	return nil
}

func sendSSE(w *bufio.Writer, event string, data interface{}) {
	jsonData, _ := json.Marshal(data)
	fmt.Fprintf(w, "event: %s\n", event)
	fmt.Fprintf(w, "data: %s\n\n", string(jsonData))
	w.Flush()
}

func (s *Server) handleListDocuments(c *fiber.Ctx) error {
	docs, err := db.ListDocuments()
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "Failed to list documents"})
	}
	return c.JSON(docs)
}

func (s *Server) handleGetDocument(c *fiber.Ctx) error {
	id, err := c.ParamsInt("id")
	if err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid ID"})
	}

	doc, err := db.GetDocument(id)
	if err != nil {
		return c.Status(404).JSON(fiber.Map{"error": "Document not found"})
	}

	return c.JSON(doc)
}

func (s *Server) handleSearch(c *fiber.Ctx) error {
	query := c.Query("q")
	if query == "" {
		return c.Status(400).JSON(fiber.Map{"error": "Query required"})
	}

	limit := c.QueryInt("limit", 10)
	results, err := db.Search(query, limit)
	if err != nil {
		return c.Status(500).JSON(fiber.Map{"error": "Search failed"})
	}

	return c.JSON(results)
}

func (s *Server) handleListSessions(c *fiber.Ctx) error {
	sessions := s.chatManager.ListSessions()
	return c.JSON(sessions)
}

func (s *Server) handleGetSession(c *fiber.Ctx) error {
	id := c.Params("id")
	session := s.chatManager.GetSession(id)
	if session == nil {
		return c.Status(404).JSON(fiber.Map{"error": "Session not found"})
	}
	return c.JSON(session)
}

// ═══════════════════════════════════════════════════════════════════
// REGEX HANDLERS
// ═══════════════════════════════════════════════════════════════════

type TextRequest struct {
	Text string `json:"text"`
}

func (s *Server) handleRegexExtract(c *fiber.Ctx) error {
	var req TextRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	if req.Text == "" {
		return c.Status(400).JSON(fiber.Map{"error": "Text required"})
	}

	matches := s.regexMatcher.FindAll(req.Text)

	// Group by category
	grouped := make(map[string][]regex.Match)
	for _, m := range matches {
		grouped[m.Category] = append(grouped[m.Category], m)
	}

	return c.JSON(fiber.Map{
		"total":   len(matches),
		"matches": grouped,
	})
}

func (s *Server) handleRegexExtractCategory(c *fiber.Ctx) error {
	category := c.Params("category")

	var req TextRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	matches := s.regexMatcher.FindByCategory(req.Text, category)

	return c.JSON(fiber.Map{
		"category": category,
		"total":    len(matches),
		"matches":  matches,
	})
}

func (s *Server) handleRegexSensitive(c *fiber.Ctx) error {
	var req TextRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	matches := s.regexMatcher.FindSensitive(req.Text)

	return c.JSON(fiber.Map{
		"warning":   "Sensitive data detected!",
		"total":     len(matches),
		"matches":   matches,
	})
}

func (s *Server) handleRegexRedact(c *fiber.Ctx) error {
	var req TextRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(400).JSON(fiber.Map{"error": "Invalid request"})
	}

	redacted := regex.RedactSensitive(req.Text)
	sensitiveMatches := s.regexMatcher.FindSensitive(req.Text)

	return c.JSON(fiber.Map{
		"original":      req.Text,
		"redacted":      redacted,
		"items_redacted": len(sensitiveMatches),
	})
}

func (s *Server) Listen(addr string) error {
	log.Printf("[API] Starting server on %s", addr)
	return s.app.Listen(addr)
}
