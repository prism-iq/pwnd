package main

import (
	"log"
	"os"
	"strconv"

	"hybridcore/internal/api"
	"hybridcore/internal/chat"
	"hybridcore/internal/db"
	"hybridcore/internal/llm"
	"hybridcore/internal/rag"
)

func main() {
	log.Println("=== HybridCore 2.0 ===")
	log.Println("Zero-cost OSINT platform with local LLM")

	// Configuration from environment
	dbHost := getEnv("DB_HOST", "localhost")
	dbPort := getEnvInt("DB_PORT", 5432)
	dbUser := getEnv("DB_USER", "hybridcore")
	dbPass := getEnv("DB_PASS", "hc_secure_2026!")
	dbName := getEnv("DB_NAME", "hybridcore")

	llmHost := getEnv("LLM_HOST", "127.0.0.1")
	llmPort := getEnvInt("LLM_PORT", 8001)

	serverPort := getEnv("PORT", "8080")

	// Connect to PostgreSQL
	log.Println("[DB] Connecting to PostgreSQL...")
	if err := db.Connect(dbHost, dbPort, dbUser, dbPass, dbName); err != nil {
		log.Fatalf("[DB] Failed to connect: %v", err)
	}

	// Initialize LLM client
	log.Printf("[LLM] Connecting to local LLM at %s:%d...", llmHost, llmPort)
	llmClient := llm.NewClient(llmHost, llmPort)

	// Check LLM health
	health, err := llmClient.Health()
	if err != nil {
		log.Printf("[LLM] Warning: LLM not available: %v", err)
	} else {
		log.Printf("[LLM] Connected! Model: %s, Ready: %v", health.Model, health.Ready)
	}

	// Initialize RAG engine
	ragEngine := rag.NewEngine(llmClient)

	// Initialize chat manager
	chatManager := chat.NewManager(ragEngine, llmClient)

	// Show stats
	stats := ragEngine.GetStats()
	log.Printf("[Stats] Documents: %v, Entities: %v, Edges: %v",
		stats["documents"], stats["entities"], stats["edges"])

	// Start server
	server := api.NewServer(chatManager, ragEngine)
	log.Printf("[Server] Starting on :%s", serverPort)

	if err := server.Listen(":" + serverPort); err != nil {
		log.Fatalf("[Server] Failed to start: %v", err)
	}
}

func getEnv(key, defaultVal string) string {
	if val := os.Getenv(key); val != "" {
		return val
	}
	return defaultVal
}

func getEnvInt(key string, defaultVal int) int {
	if val := os.Getenv(key); val != "" {
		if i, err := strconv.Atoi(val); err == nil {
			return i
		}
	}
	return defaultVal
}
