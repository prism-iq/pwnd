package llm

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Client struct {
	baseURL    string
	httpClient *http.Client
}

type GenerateRequest struct {
	Prompt      string  `json:"prompt"`
	MaxTokens   int     `json:"max_tokens,omitempty"`
	Temperature float64 `json:"temperature,omitempty"`
}

type GenerateResponse struct {
	Text       string `json:"text"`
	TokensUsed int    `json:"tokens_used"`
	Error      string `json:"error,omitempty"`
}

type IntentRequest struct {
	Query string `json:"query"`
}

type IntentResponse struct {
	Intent struct {
		Intent   string   `json:"intent"`
		Entities []string `json:"entities"`
		Filters  map[string]interface{} `json:"filters"`
	} `json:"intent"`
	Raw   string `json:"raw,omitempty"`
	Error string `json:"error,omitempty"`
}

type AnalyzeRequest struct {
	Query   string `json:"query"`
	Context string `json:"context"`
}

type AnalyzeResponse struct {
	Analysis         string   `json:"analysis"`
	SuggestedQueries []string `json:"suggested_queries"`
	TokensUsed       int      `json:"tokens_used"`
	Error            string   `json:"error,omitempty"`
}

type HealthResponse struct {
	Status string `json:"status"`
	Model  string `json:"model"`
	Ready  bool   `json:"ready"`
}

func NewClient(host string, port int) *Client {
	return &Client{
		baseURL: fmt.Sprintf("http://%s:%d", host, port),
		httpClient: &http.Client{
			Timeout: 120 * time.Second,
		},
	}
}

func (c *Client) Health() (*HealthResponse, error) {
	resp, err := c.httpClient.Get(c.baseURL + "/health")
	if err != nil {
		return nil, fmt.Errorf("health check failed: %w", err)
	}
	defer resp.Body.Close()

	var health HealthResponse
	if err := json.NewDecoder(resp.Body).Decode(&health); err != nil {
		return nil, fmt.Errorf("decode health: %w", err)
	}

	return &health, nil
}

func (c *Client) Generate(prompt string, maxTokens int, temperature float64) (*GenerateResponse, error) {
	if maxTokens == 0 {
		maxTokens = 500
	}
	if temperature == 0 {
		temperature = 0.3
	}

	req := GenerateRequest{
		Prompt:      prompt,
		MaxTokens:   maxTokens,
		Temperature: temperature,
	}

	body, err := c.postRaw("/generate", req)
	if err != nil {
		return nil, err
	}

	var resp GenerateResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode generate response: %w", err)
	}

	return &resp, nil
}

func (c *Client) ParseIntent(query string) (*IntentResponse, error) {
	req := IntentRequest{Query: query}

	body, err := c.postRaw("/parse_intent", req)
	if err != nil {
		return nil, err
	}

	var resp IntentResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode intent response: %w", err)
	}

	return &resp, nil
}

func (c *Client) Analyze(query, context string) (*AnalyzeResponse, error) {
	req := AnalyzeRequest{
		Query:   query,
		Context: context,
	}

	body, err := c.postRaw("/analyze", req)
	if err != nil {
		return nil, err
	}

	var resp AnalyzeResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("decode analyze response: %w", err)
	}

	return &resp, nil
}

func (c *Client) postRaw(path string, reqBody interface{}) ([]byte, error) {
	data, err := json.Marshal(reqBody)
	if err != nil {
		return nil, fmt.Errorf("marshal request: %w", err)
	}

	resp, err := c.httpClient.Post(c.baseURL+path, "application/json", bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("post %s: %w", path, err)
	}
	defer resp.Body.Close()

	return io.ReadAll(resp.Body)
}
