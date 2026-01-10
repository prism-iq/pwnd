# BRAINSTORMING.md

> **Purpose:** Strategic thinking space for project evolution
> **Updated:** 2026-01-10
> **Use this file** when planning features, solving problems, or exploring ideas

---

## Current State Assessment

### What Works Well
- RAG chat with source citations
- 33,598 documents indexed and searchable
- PostgreSQL with connection pooling
- Dual LLM fallback (Phi-3 → Haiku)
- Clean dark theme UI
- One-command install

### What Needs Improvement
- Chat streaming is slow (generates full response first)
- Conversation titles are all "New Chat"
- No semantic search (only keyword FTS)
- Graph visualization needs work
- Mobile responsiveness

---

## Feature Ideas

### High Priority

#### 1. Smart Conversation Titles
```
Problem: All conversations show "New Chat"
Solution: Extract title from first user message
Implementation:
- In save_message(), if role="user" and no title exists
- Use first 50 chars of message as title
- Or use LLM to generate 3-5 word summary
```

#### 2. True Streaming Responses
```
Problem: /api/chat/stream generates full response, then chunks it
Solution: Stream from LLM directly
Implementation:
- Modify llm_client.py to yield tokens
- Use async generator in routes_chat.py
- Send chunks as they arrive
```

#### 3. Semantic Search (Embeddings)
```
Problem: Only keyword search, misses semantic matches
Solution: Add vector embeddings
Implementation:
- Generate embeddings for all documents (sentence-transformers)
- Store in PostgreSQL with pgvector
- Hybrid search: FTS + vector similarity
Cost: ~$5-10 for embedding 33k docs with local model
```

#### 4. Citation Links in Chat
```
Problem: Sources shown but not clickable
Solution: Link to /source.html?id=X
Implementation:
- Modify chat.html to render source links
- Add onclick handler to open document viewer
```

### Medium Priority

#### 5. Export Conversation
```
Feature: Download conversation as PDF/Markdown
Implementation:
- Add export button in chat UI
- Endpoint: GET /api/chat/conversations/:id/export?format=md
- Include sources and timestamps
```

#### 6. Voice Input
```
Feature: Speech-to-text for queries
Implementation:
- Web Speech API (browser native)
- Add microphone button to chat input
- No backend changes needed
```

#### 7. Document Upload
```
Feature: Users upload documents to investigate
Implementation:
- /api/documents/upload endpoint
- Process with existing pipeline
- Add to user's private collection
```

#### 8. Multi-language Support
```
Feature: French, Spanish, German queries
Implementation:
- Detect language in query
- Translate to English for search
- Translate response back
- Use local translation model or API
```

### Low Priority / Future

#### 9. Knowledge Graph Visualization
```
Feature: Interactive entity relationship map
Implementation:
- D3.js or Cytoscape.js
- Show connections between people, places, dates
- Filter by entity type
- Click to investigate
```

#### 10. Timeline View
```
Feature: Chronological event display
Implementation:
- Extract dates from documents
- Plot on interactive timeline
- Click to see documents from that date
```

#### 11. Collaborative Investigation
```
Feature: Multiple users share investigation
Implementation:
- Shared conversation rooms
- WebSocket for real-time sync
- User permissions (read/write)
```

#### 12. API for Developers
```
Feature: Public API with rate limiting
Implementation:
- API keys for external access
- Documentation (OpenAPI/Swagger)
- Usage tracking and quotas
```

---

## Technical Debt

### Must Fix Soon
1. **Error handling in chat** - Silent failures, need user feedback
2. **Connection pool exhaustion** - Add monitoring
3. **Log rotation** - Logs grow unbounded

### Should Fix
1. **Type hints** - Add throughout codebase
2. **Tests** - No test coverage currently
3. **Documentation** - API docs incomplete

### Nice to Have
1. **CI/CD** - GitHub Actions for deploy
2. **Monitoring** - Prometheus + Grafana
3. **Backup** - Automated PostgreSQL backups

---

## Investigation Enhancements

### Evidence Scoring Improvements
```
Current: Manual scores in prosecution.py
Ideas:
- Auto-score based on document frequency
- Weight by source reliability
- Track evidence chains
- Generate confidence intervals
```

### Cross-Reference Detection
```
Feature: Find documents that mention same entities
Implementation:
- Extract entities from each doc
- Build co-occurrence matrix
- Surface unexpected connections
```

### Anomaly Detection
```
Feature: Find unusual patterns
Ideas:
- Flights to same location by different people
- Financial transactions above threshold
- Communication patterns (who talks to who)
- Timeline gaps (missing documents)
```

---

## Performance Optimizations

### Database
- [ ] Add indexes for common queries
- [ ] Partition large tables by date
- [ ] Implement query caching (Redis)
- [ ] Connection pool tuning

### LLM
- [ ] Cache common question answers
- [ ] Batch similar queries
- [ ] Use smaller model for simple questions
- [ ] Precompute entity extractions

### Frontend
- [ ] Lazy load conversation history
- [ ] Virtual scrolling for long chats
- [ ] Service worker for offline
- [ ] Compress assets

---

## User Experience Ideas

### Chat Improvements
- Suggested follow-up questions
- "Ask about X" buttons on documents
- Share conversation via link
- Pin important conversations

### Search Improvements
- Search filters (date range, document type)
- Saved searches
- Search history
- Related searches suggestions

### Navigation
- Breadcrumb trail
- Recent documents sidebar
- Bookmarks / favorites
- Quick entity lookup

---

## Security Considerations

### Current Security
- Rate limiting (100/min)
- Security headers (CSP, XSS, etc.)
- Parameterized queries
- JWT authentication

### TODO Security
- [ ] Audit logging for sensitive queries
- [ ] IP-based blocking for abuse
- [ ] CAPTCHA for registration
- [ ] Two-factor authentication
- [ ] Data encryption at rest

---

## Questions to Explore

1. **Can we identify redacted content?** - OCR patterns, black boxes
2. **Are there document clusters?** - Unsupervised clustering
3. **What's missing?** - Gaps in timeline, expected but absent docs
4. **Who's connected but not named?** - Indirect relationships
5. **What patterns repeat?** - Similar events across time

---

## Immediate Next Steps

### This Week
1. Fix conversation titles (use first message)
2. Make source citations clickable
3. Add basic error handling to chat

### This Month
1. Semantic search with embeddings
2. True LLM streaming
3. Export conversation feature

### This Quarter
1. Knowledge graph visualization
2. Timeline view
3. Multi-language support

---

## Random Ideas (Unfiltered)

- Discord bot for queries
- Telegram integration
- Browser extension to highlight names on any page
- Automated daily digest email
- RSS feed of new findings
- Podcast transcription integration
- Social media monitoring (mentions of targets)
- Court filing tracker
- FOIA request generator
- Evidence package builder for journalists

---

## Resources & References

- pgvector: https://github.com/pgvector/pgvector
- sentence-transformers: https://www.sbert.net/
- D3.js: https://d3js.org/
- Cytoscape.js: https://js.cytoscape.org/
- Web Speech API: https://developer.mozilla.org/en-US/docs/Web/API/Web_Speech_API

---

*Add ideas here whenever they come up. Review periodically.*
