# Detective Methodology - Criminal Investigation

## Investigation Workflow

### Step 1: Query Analysis
- Parse user question
- Identify keywords
- Detect investigation type:
  - **Search**: Find information about entity
  - **Connections**: Map relationships
  - **Timeline**: Chronological reconstruction

### Step 2: Corpus Search
- FTS5 full-text search
- Graph traversal (if connections)
- Sort by relevance (rank)
- Limit to top 10 results

### Step 3: Criminal Analysis (Haiku)
**Focus areas:**
1. **Pedocriminality Indicators**
   - Minors mentioned + sexual/inappropriate context
   - Grooming patterns (gradual trust building)
   - Age gaps in communications
   - Coded language

2. **Violence Indicators**
   - Threats (explicit or implied)
   - Domination language
   - Blackmail/coercion
   - Power imbalance

3. **Trafficking Indicators**
   - Money transfers (amounts, frequency)
   - Geographic movement patterns
   - Multiple identities/aliases
   - Recruiting language

4. **Abuse Patterns**
   - Frequency of contact
   - Escalation over time
   - Isolation tactics
   - Control mechanisms

### Step 4: Response Formatting
- Factual summary
- Timeline reconstruction
- Network mapping (connections)
- Criminal indicators (if detected)
- Hypotheses (clearly marked)
- Sources cited [#ID]

## Red Flags (Auto-Alert)
- Minor + adult + travel
- Financial transactions + obscure purposes
- Encrypted/coded communications
- Multiple aliases same person
- Unusual power dynamics

## Evidence Standards
1. **Direct evidence**: Quote exact text [#ID]
2. **Circumstantial**: Pattern from multiple sources [#ID1, #ID2, ...]
3. **Hypothesis**: Logical inference, clearly marked "HYPOTHESIS"
4. **No evidence**: Say "insufficient data"

## Victim Protection
- Anonymize minors: "Minor A", "Minor B"
- Redact identifying details if victim
- Prioritize safety over investigation
- Report findings, don't judge

## Chain of Custody
- Every fact → source [#ID]
- Timestamps preserved
- Metadata tracked
- Traceable path: query → search → result → analysis
