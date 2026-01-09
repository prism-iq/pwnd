# Graph Enrichment Script

Extract entities, relationships and forensic signals from emails using Claude Haiku.

## Features

- **Entity Extraction**: Persons, emails, companies, locations, amounts, dates, etc.
- **Relationship Detection**: Ownership, collaboration, travel, communication patterns
- **Forensic Signals**: Code words, vague references, timing anomalies, urgency, deletion requests
- **Smart Resume**: Skip already processed emails
- **Cost Tracking**: Real-time token usage and cost estimation
- **Batch Processing**: Process 5 emails per Haiku call (configurable)

## Usage

### Test Mode (Dry-Run)
```bash
# Test with 5 emails without inserting data
python scripts/enrich_graph.py --limit 5 --dry-run

# Test with 10 emails
python scripts/enrich_graph.py --limit 10 --dry-run
```

### Production Mode
```bash
# Process 100 emails
python scripts/enrich_graph.py --limit 100

# Process all unprocessed emails (auto-resume)
python scripts/enrich_graph.py

# Force reprocess all emails (ignore audit log)
python scripts/enrich_graph.py --no-resume

# Custom batch size
python scripts/enrich_graph.py --limit 50 --batch-size 3
```

## What Gets Extracted

### Entities (Nodes)
- **People**: Names normalized ("John Smith" not "JOHN SMITH")
- **Contacts**: Email addresses, phone numbers
- **Organizations**: Companies, organizations
- **Places**: Locations, addresses, properties
- **Financial**: Amounts with currency ($5,000, €10K)
- **Temporal**: Dates, times, timestamps
- **Objects**: Vehicles, aircraft (with registration), documents
- **Events**: Meetings, flights, trips, transactions
- **Statements**: Claims, quotes, instructions, plans, denials, threats

### Relationships (Edges)
- Ownership (owns, has_email, has_property)
- Communication (sent_to, called, contacted)
- Collaboration (works_for, partner_with, collaborating_with)
- Movement (traveling_to, flew_to, visited)
- Financial (paid, transferred, received)
- Social (friend_of, knows, met_with)
- Accusations (accuses, claims_about, denies)

### Forensic Signals (Flags)
- **Timing Anomalies**: Emails at 3am, ultra-fast responses
- **Code Words**: Out-of-context repeated words
- **Vague References**: "the thing", "you know who"
- **Urgency Markers**: "ASAP", "immediately", unusual pressure
- **Deletion Requests**: "delete this", "destroy"
- **Financial Flags**: Cash mentions, offshore references
- **Language Switches**: Mid-email language changes

## Database Impact

### graph.db
- Nodes inserted with deduplication
- Edges inserted with deduplication
- Properties linked to nodes

### scores.db
- Flags inserted as severity=0 (to be scored later)

### audit.db
- Evidence chain logs for resume capability
- Extraction stats per email

## Cost Estimation

**Example for 13,009 emails:**
- Batches: ~2,602 (5 emails/batch)
- Estimated tokens: ~8M input, ~2M output
- Estimated cost: **$3-5 USD**

**Per email average:**
- Input: ~600 tokens
- Output: ~150 tokens
- Cost: ~$0.0004 per email

## Resume Capability

The script automatically tracks processed emails in `audit.db`. When rerun:
1. Checks `evidence_chain` table for `batch_extracted` action
2. Skips already processed email IDs
3. Only processes new/unprocessed emails

To force reprocessing: `--no-resume`

## Output Example

```
================================================================================
EXTRACTION COMPLETE
================================================================================

Emails processed:    100
Haiku calls:         20
Input tokens:        62,847
Output tokens:       15,234
Estimated cost:      $0.1106

Nodes created:       847
Edges created:       423
Properties created:  12
Signals flagged:     3

Time elapsed:        142.5s
================================================================================
```

## Troubleshooting

### "No emails to process"
All emails already extracted. Use `--no-resume` to reprocess.

### API Rate Limits
Script has 1s delay between batches. Increase `--batch-size` to process faster (but more tokens per call).

### Out of Memory
Reduce `--batch-size` to 3 or use `--limit` to process in chunks.

### Invalid JSON Response
Haiku sometimes returns malformed JSON. Script will retry 3x with exponential backoff.

## Next Steps

After enrichment:
1. Run `scripts/score_graph.py` to calculate confidence scores
2. Use `/api/ask?q=qui connait trump` to query connections
3. Explore graph in UI or via `/api/nodes` endpoints
