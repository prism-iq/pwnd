package nlp

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// Client for Python NLP Engine
type Client struct {
	baseURL    string
	httpClient *http.Client
}

type Entity struct {
	Value      string  `json:"value"`
	Start      int     `json:"start"`
	End        int     `json:"end"`
	Confidence float64 `json:"confidence"`
}

type ExtractResponse struct {
	Entities map[string][]Entity `json:"entities"`
}

type AnalyzeResponse struct {
	Stats struct {
		CharCount     int     `json:"char_count"`
		WordCount     int     `json:"word_count"`
		SentenceCount int     `json:"sentence_count"`
		AvgWordLength float64 `json:"avg_word_length"`
		Language      string  `json:"language"`
	} `json:"stats"`
	Entities     map[string][]Entity `json:"entities"`
	EntityCounts map[string]int      `json:"entity_counts"`
	Keywords     []struct {
		Word  string `json:"word"`
		Count int    `json:"count"`
	} `json:"keywords"`
}

type Relationship struct {
	From struct {
		Type  string `json:"type"`
		Value string `json:"value"`
	} `json:"from"`
	To struct {
		Type  string `json:"type"`
		Value string `json:"value"`
	} `json:"to"`
	Relationship string `json:"relationship"`
	Context      string `json:"context"`
	Distance     int    `json:"distance"`
}

type RelationshipsResponse struct {
	Entities      map[string][]Entity `json:"entities"`
	Relationships []Relationship      `json:"relationships"`
}

func NewClient(host string, port int) *Client {
	return &Client{
		baseURL: fmt.Sprintf("http://%s:%d", host, port),
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

func (c *Client) Health() (bool, error) {
	resp, err := c.httpClient.Get(c.baseURL + "/health")
	if err != nil {
		return false, err
	}
	defer resp.Body.Close()
	return resp.StatusCode == 200, nil
}

func (c *Client) Extract(text string) (*ExtractResponse, error) {
	body, err := c.post("/extract", map[string]string{"text": text})
	if err != nil {
		return nil, err
	}

	var result ExtractResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) Analyze(text string) (*AnalyzeResponse, error) {
	body, err := c.post("/analyze", map[string]string{"text": text})
	if err != nil {
		return nil, err
	}

	var result AnalyzeResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) Relationships(text string) (*RelationshipsResponse, error) {
	body, err := c.post("/relationships", map[string]string{"text": text})
	if err != nil {
		return nil, err
	}

	var result RelationshipsResponse
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, err
	}
	return &result, nil
}

func (c *Client) post(path string, data interface{}) ([]byte, error) {
	jsonData, err := json.Marshal(data)
	if err != nil {
		return nil, err
	}

	resp, err := c.httpClient.Post(c.baseURL+path, "application/json", bytes.NewReader(jsonData))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	return io.ReadAll(resp.Body)
}
