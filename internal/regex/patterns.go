package regex

import (
	"regexp"
	"strings"
	"sync"
)

// ═══════════════════════════════════════════════════════════════════
// COMPILED REGEX PATTERNS - Pre-compiled for maximum performance
// ═══════════════════════════════════════════════════════════════════

var (
	// Communication patterns
	EmailRegex    = regexp.MustCompile(`(?i)\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b`)
	PhoneRegex    = regexp.MustCompile(`(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,4}`)
	URLRegex      = regexp.MustCompile(`(?i)https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)`)
	IPRegex       = regexp.MustCompile(`\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b`)
	IPv6Regex     = regexp.MustCompile(`(?i)(?:[0-9a-f]{1,4}:){7}[0-9a-f]{1,4}|(?:[0-9a-f]{1,4}:){1,7}:|(?:[0-9a-f]{1,4}:){1,6}:[0-9a-f]{1,4}`)
	MACRegex      = regexp.MustCompile(`(?i)(?:[0-9A-F]{2}[:-]){5}[0-9A-F]{2}`)

	// Dates and times
	DateISORegex   = regexp.MustCompile(`\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?`)
	DateEURegex    = regexp.MustCompile(`\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}`)
	DateTextRegex  = regexp.MustCompile(`(?i)\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}\b`)
	TimeRegex      = regexp.MustCompile(`\b(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\s*(?:AM|PM|am|pm)?\b`)

	// Financial
	CurrencyRegex  = regexp.MustCompile(`(?i)[$€£¥₿]\s*\d+(?:[.,]\d{2,3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{3})*(?:[.,]\d{2})?\s*(?:USD|EUR|GBP|BTC|ETH|USDT)`)
	BTCAddrRegex   = regexp.MustCompile(`\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b`)
	ETHAddrRegex   = regexp.MustCompile(`\b0x[a-fA-F0-9]{40}\b`)
	IBANRegex      = regexp.MustCompile(`\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]?){0,16}\b`)
	CreditCardRegex = regexp.MustCompile(`\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b`)

	// Social
	TwitterRegex   = regexp.MustCompile(`@[A-Za-z0-9_]{1,15}\b`)
	HashtagRegex   = regexp.MustCompile(`#[A-Za-z0-9_]+\b`)
	MentionRegex   = regexp.MustCompile(`@[A-Za-z0-9_.]+`)

	// Technical
	UUIDRegex      = regexp.MustCompile(`(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b`)
	MD5Regex       = regexp.MustCompile(`\b[a-fA-F0-9]{32}\b`)
	SHA1Regex      = regexp.MustCompile(`\b[a-fA-F0-9]{40}\b`)
	SHA256Regex    = regexp.MustCompile(`\b[a-fA-F0-9]{64}\b`)
	Base64Regex    = regexp.MustCompile(`(?:[A-Za-z0-9+/]{4}){10,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?`)
	JWTRegex       = regexp.MustCompile(`eyJ[A-Za-z0-9_-]*\.eyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]*`)

	// Code patterns
	FunctionCallRegex = regexp.MustCompile(`\b[a-zA-Z_][a-zA-Z0-9_]*\s*\([^)]*\)`)
	ImportRegex       = regexp.MustCompile(`(?m)^(?:import|from|require|use|include)\s+.+$`)
	CommentRegex      = regexp.MustCompile(`(?s)(?://.*?$|/\*.*?\*/|#.*?$)`)
	StringLiteralRegex = regexp.MustCompile(`"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'`)

	// Security
	PasswordRegex  = regexp.MustCompile(`(?i)(?:password|passwd|pwd|secret|api[_-]?key|token|auth)\s*[:=]\s*['"]?[^\s'"]+`)
	PrivateKeyRegex = regexp.MustCompile(`-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----`)
	AWSKeyRegex    = regexp.MustCompile(`(?i)AKIA[0-9A-Z]{16}`)
	GitHubTokenRegex = regexp.MustCompile(`ghp_[a-zA-Z0-9]{36}`)

	// Names and places (heuristic)
	PersonNameRegex = regexp.MustCompile(`\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b`)
	OrgRegex        = regexp.MustCompile(`(?i)\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+(?:Inc|Corp|LLC|Ltd|GmbH|SA|SAS|SARL|Co|Company|Foundation|Institute|University|Association)\b`)

	// File paths and URLs
	FilePathRegex   = regexp.MustCompile(`(?:/[a-zA-Z0-9._-]+)+|(?:[A-Z]:\\(?:[a-zA-Z0-9._-]+\\?)+)`)
	DomainRegex     = regexp.MustCompile(`(?i)\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}\b`)
)

// ═══════════════════════════════════════════════════════════════════
// PATTERN REGISTRY
// ═══════════════════════════════════════════════════════════════════

type Pattern struct {
	Name       string
	Regex      *regexp.Regexp
	Category   string
	Confidence float64
	Sensitive  bool
}

var AllPatterns = []Pattern{
	// Communication
	{"email", EmailRegex, "communication", 0.95, false},
	{"phone", PhoneRegex, "communication", 0.70, false},
	{"url", URLRegex, "communication", 0.95, false},
	{"ip_address", IPRegex, "network", 0.99, false},
	{"ipv6_address", IPv6Regex, "network", 0.99, false},
	{"mac_address", MACRegex, "network", 0.95, false},

	// Dates
	{"date_iso", DateISORegex, "temporal", 0.95, false},
	{"date_eu", DateEURegex, "temporal", 0.70, false},
	{"date_text", DateTextRegex, "temporal", 0.80, false},
	{"time", TimeRegex, "temporal", 0.75, false},

	// Financial
	{"currency", CurrencyRegex, "financial", 0.85, true},
	{"btc_address", BTCAddrRegex, "crypto", 0.90, true},
	{"eth_address", ETHAddrRegex, "crypto", 0.95, true},
	{"iban", IBANRegex, "financial", 0.95, true},
	{"credit_card", CreditCardRegex, "financial", 0.90, true},

	// Social
	{"twitter_handle", TwitterRegex, "social", 0.90, false},
	{"hashtag", HashtagRegex, "social", 0.95, false},
	{"mention", MentionRegex, "social", 0.85, false},

	// Technical
	{"uuid", UUIDRegex, "identifier", 0.99, false},
	{"md5_hash", MD5Regex, "hash", 0.80, false},
	{"sha1_hash", SHA1Regex, "hash", 0.85, false},
	{"sha256_hash", SHA256Regex, "hash", 0.90, false},
	{"base64", Base64Regex, "encoding", 0.60, false},
	{"jwt", JWTRegex, "auth", 0.95, true},

	// Code
	{"function_call", FunctionCallRegex, "code", 0.75, false},
	{"import_statement", ImportRegex, "code", 0.90, false},

	// Security
	{"password_leak", PasswordRegex, "security", 0.80, true},
	{"private_key", PrivateKeyRegex, "security", 0.99, true},
	{"aws_key", AWSKeyRegex, "security", 0.95, true},
	{"github_token", GitHubTokenRegex, "security", 0.99, true},

	// Entities
	{"person_name", PersonNameRegex, "entity", 0.50, false},
	{"organization", OrgRegex, "entity", 0.60, false},
	{"file_path", FilePathRegex, "filesystem", 0.80, false},
	{"domain", DomainRegex, "network", 0.85, false},
}

// ═══════════════════════════════════════════════════════════════════
// MATCHER ENGINE
// ═══════════════════════════════════════════════════════════════════

type Match struct {
	Pattern    string  `json:"pattern"`
	Category   string  `json:"category"`
	Value      string  `json:"value"`
	Start      int     `json:"start"`
	End        int     `json:"end"`
	Confidence float64 `json:"confidence"`
	Sensitive  bool    `json:"sensitive"`
}

type Matcher struct {
	patterns []Pattern
	cache    sync.Map
}

func NewMatcher() *Matcher {
	return &Matcher{
		patterns: AllPatterns,
	}
}

func (m *Matcher) FindAll(text string) []Match {
	var matches []Match
	var mu sync.Mutex
	var wg sync.WaitGroup

	// Parallel regex matching
	for _, p := range m.patterns {
		wg.Add(1)
		go func(pattern Pattern) {
			defer wg.Done()

			found := pattern.Regex.FindAllStringIndex(text, -1)
			if found == nil {
				return
			}

			mu.Lock()
			for _, loc := range found {
				matches = append(matches, Match{
					Pattern:    pattern.Name,
					Category:   pattern.Category,
					Value:      text[loc[0]:loc[1]],
					Start:      loc[0],
					End:        loc[1],
					Confidence: pattern.Confidence,
					Sensitive:  pattern.Sensitive,
				})
			}
			mu.Unlock()
		}(p)
	}

	wg.Wait()
	return matches
}

func (m *Matcher) FindByCategory(text string, category string) []Match {
	var matches []Match

	for _, p := range m.patterns {
		if p.Category != category {
			continue
		}

		found := p.Regex.FindAllStringIndex(text, -1)
		for _, loc := range found {
			matches = append(matches, Match{
				Pattern:    p.Name,
				Category:   p.Category,
				Value:      text[loc[0]:loc[1]],
				Start:      loc[0],
				End:        loc[1],
				Confidence: p.Confidence,
				Sensitive:  p.Sensitive,
			})
		}
	}

	return matches
}

func (m *Matcher) FindSensitive(text string) []Match {
	var matches []Match

	for _, p := range m.patterns {
		if !p.Sensitive {
			continue
		}

		found := p.Regex.FindAllStringIndex(text, -1)
		for _, loc := range found {
			matches = append(matches, Match{
				Pattern:    p.Name,
				Category:   p.Category,
				Value:      text[loc[0]:loc[1]],
				Start:      loc[0],
				End:        loc[1],
				Confidence: p.Confidence,
				Sensitive:  true,
			})
		}
	}

	return matches
}

// ═══════════════════════════════════════════════════════════════════
// TEXT TRANSFORMATIONS
// ═══════════════════════════════════════════════════════════════════

var (
	WhitespaceRegex  = regexp.MustCompile(`\s+`)
	PunctuationRegex = regexp.MustCompile(`[^\w\s]`)
	NumbersRegex     = regexp.MustCompile(`\d+`)
	HTMLTagRegex     = regexp.MustCompile(`<[^>]+>`)
	AnsiEscapeRegex  = regexp.MustCompile(`\x1b\[[0-9;]*m`)
)

func NormalizeWhitespace(text string) string {
	return strings.TrimSpace(WhitespaceRegex.ReplaceAllString(text, " "))
}

func RemovePunctuation(text string) string {
	return PunctuationRegex.ReplaceAllString(text, "")
}

func RemoveNumbers(text string) string {
	return NumbersRegex.ReplaceAllString(text, "")
}

func StripHTML(text string) string {
	return HTMLTagRegex.ReplaceAllString(text, "")
}

func StripAnsi(text string) string {
	return AnsiEscapeRegex.ReplaceAllString(text, "")
}

func RedactSensitive(text string) string {
	result := text
	m := NewMatcher()
	matches := m.FindSensitive(text)

	// Sort by position descending to preserve indices
	for i := len(matches) - 1; i >= 0; i-- {
		match := matches[i]
		redacted := strings.Repeat("*", len(match.Value))
		result = result[:match.Start] + redacted + result[match.End:]
	}

	return result
}
