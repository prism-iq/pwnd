package chat

import (
	"log"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"

	"hybridcore/internal/llm"
	"hybridcore/internal/rag"
)

type Manager struct {
	sessions  map[string]*Session
	mu        sync.RWMutex
	ragEngine *rag.Engine
	llmClient *llm.Client
}

type Session struct {
	ID        string    `json:"id"`
	Messages  []Message `json:"messages"`
	CreatedAt time.Time `json:"created_at"`
	UpdatedAt time.Time `json:"updated_at"`
}

type Message struct {
	Role      string    `json:"role"`
	Content   string    `json:"content"`
	Sources   []rag.Source `json:"sources,omitempty"`
	Timestamp time.Time `json:"timestamp"`
}

type ChatRequest struct {
	SessionID string `json:"session_id"`
	Message   string `json:"message"`
	UseRAG    *bool  `json:"use_rag,omitempty"`
}

type ChatResponse struct {
	SessionID        string       `json:"session_id"`
	Message          string       `json:"message"`
	Sources          []rag.Source `json:"sources,omitempty"`
	SuggestedQueries []string     `json:"suggested_queries,omitempty"`
}

func NewManager(ragEngine *rag.Engine, llmClient *llm.Client) *Manager {
	return &Manager{
		sessions:  make(map[string]*Session),
		ragEngine: ragEngine,
		llmClient: llmClient,
	}
}

func (m *Manager) GetOrCreateSession(sessionID string) *Session {
	m.mu.Lock()
	defer m.mu.Unlock()

	if sessionID != "" {
		if s, ok := m.sessions[sessionID]; ok {
			return s
		}
	}

	newID := uuid.New().String()[:8]
	session := &Session{
		ID:        newID,
		Messages:  []Message{},
		CreatedAt: time.Now(),
		UpdatedAt: time.Now(),
	}

	m.sessions[newID] = session
	return session
}

func (m *Manager) Chat(req ChatRequest) (*ChatResponse, error) {
	session := m.GetOrCreateSession(req.SessionID)

	// Add user message
	session.Messages = append(session.Messages, Message{
		Role:      "user",
		Content:   req.Message,
		Timestamp: time.Now(),
	})
	session.UpdatedAt = time.Now()

	// Determine if RAG should be used
	useRAG := true
	if req.UseRAG != nil {
		useRAG = *req.UseRAG
	}

	var response *ChatResponse

	// Check for greetings first
	if isGreeting(req.Message) {
		response = &ChatResponse{
			SessionID: session.ID,
			Message:   getGreetingResponse(),
		}
	} else if useRAG {
		// Use RAG engine
		result, err := m.ragEngine.Query(req.Message, 5)
		if err != nil {
			log.Printf("[Chat] RAG error: %v", err)
			response = &ChatResponse{
				SessionID: session.ID,
				Message:   "Désolé, une erreur s'est produite. Réessayez.",
			}
		} else {
			response = &ChatResponse{
				SessionID:        session.ID,
				Message:          result.Answer,
				Sources:          result.Sources,
				SuggestedQueries: result.SuggestedQueries,
			}
		}
	} else {
		// Direct LLM call without RAG
		resp, err := m.llmClient.Generate(req.Message, 500, 0.3)
		if err != nil {
			log.Printf("[Chat] LLM error: %v", err)
			response = &ChatResponse{
				SessionID: session.ID,
				Message:   "Désolé, le LLM n'est pas disponible.",
			}
		} else {
			response = &ChatResponse{
				SessionID: session.ID,
				Message:   resp.Text,
			}
		}
	}

	// Add assistant message
	session.Messages = append(session.Messages, Message{
		Role:      "assistant",
		Content:   response.Message,
		Sources:   response.Sources,
		Timestamp: time.Now(),
	})

	return response, nil
}

func (m *Manager) GetSession(sessionID string) *Session {
	m.mu.RLock()
	defer m.mu.RUnlock()

	return m.sessions[sessionID]
}

func (m *Manager) ListSessions() []*Session {
	m.mu.RLock()
	defer m.mu.RUnlock()

	sessions := make([]*Session, 0, len(m.sessions))
	for _, s := range m.sessions {
		sessions = append(sessions, s)
	}
	return sessions
}

func isGreeting(msg string) bool {
	lower := strings.ToLower(strings.TrimSpace(msg))
	greetings := []string{
		"salut", "bonjour", "hello", "hi", "hey", "coucou",
		"bonsoir", "yo", "wesh", "slt",
	}

	for _, g := range greetings {
		if lower == g || strings.HasPrefix(lower, g+" ") {
			return true
		}
	}
	return false
}

func getGreetingResponse() string {
	responses := []string{
		"Bonjour! Je suis HybridCore, votre assistant OSINT. Comment puis-je vous aider?",
		"Salut! Je peux rechercher dans les documents et analyser des informations. Que cherchez-vous?",
		"Hello! Je suis prêt à vous aider avec vos recherches. Posez-moi une question!",
	}

	// Simple rotation based on time
	idx := time.Now().Unix() % int64(len(responses))
	return responses[idx]
}
