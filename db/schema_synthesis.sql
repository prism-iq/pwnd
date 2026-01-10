-- Schema for Cognitive Synthesis
-- Not storing papers. Storing understanding.
--
-- What we keep:
-- - Claims (who says what)
-- - Contradictions (who contradicts who)
-- - Connections (who cites who, who funds who)
-- - Cross-domain patterns
-- - Knowledge gaps (what we don't know yet)
--
-- Size estimate: ~100 bytes per claim = 10GB for 100M claims
-- That's 1% of your 1TB. Leaves room for everything else.

CREATE SCHEMA IF NOT EXISTS synthesis;

-- CLAIMS: What is claimed to be known
CREATE TABLE IF NOT EXISTS synthesis.claims (
    id SERIAL PRIMARY KEY,

    -- Source
    doi TEXT,                    -- Where this claim comes from
    source_title TEXT,           -- Paper title (for reference)
    source_year INTEGER,

    -- The claim itself
    claim TEXT NOT NULL,         -- The actual claim/finding
    claim_type TEXT,             -- 'finding', 'hypothesis', 'method', 'definition'

    -- Context
    field TEXT,                  -- 'neuroscience', 'math', 'biology', etc.
    subfield TEXT,

    -- Evidence strength
    evidence_type TEXT,          -- 'experimental', 'theoretical', 'review', 'meta-analysis'
    sample_size INTEGER,         -- If applicable
    confidence TEXT,             -- 'high', 'medium', 'low', 'contested'

    -- Investigation relevance
    epstein_relevant BOOLEAN DEFAULT FALSE,
    red_flags TEXT[],

    created_at TIMESTAMP DEFAULT NOW()
);

-- CONTRADICTIONS: When claims conflict
CREATE TABLE IF NOT EXISTS synthesis.contradictions (
    id SERIAL PRIMARY KEY,

    claim_a_id INTEGER REFERENCES synthesis.claims(id),
    claim_b_id INTEGER REFERENCES synthesis.claims(id),

    -- Nature of contradiction
    contradiction_type TEXT,     -- 'direct', 'methodological', 'interpretive'
    description TEXT,

    -- Resolution status
    resolved BOOLEAN DEFAULT FALSE,
    resolution TEXT,             -- How it was resolved (if known)

    created_at TIMESTAMP DEFAULT NOW()
);

-- CONNECTIONS: Who cites who, who funds who
CREATE TABLE IF NOT EXISTS synthesis.connections (
    id SERIAL PRIMARY KEY,

    -- Source
    from_doi TEXT,
    from_author TEXT,
    from_institution TEXT,
    from_year INTEGER,

    -- Target
    to_doi TEXT,
    to_author TEXT,
    to_institution TEXT,

    -- Connection type
    connection_type TEXT,        -- 'cites', 'funds', 'collaborates', 'thanks', 'disputes'

    -- Investigation relevance
    epstein_score REAL DEFAULT 0.0,

    created_at TIMESTAMP DEFAULT NOW()
);

-- PATTERNS: Cross-domain discoveries
CREATE TABLE IF NOT EXISTS synthesis.patterns (
    id SERIAL PRIMARY KEY,

    -- Pattern description
    pattern_name TEXT NOT NULL,
    description TEXT NOT NULL,

    -- Domains involved
    domains TEXT[],              -- ['neuroscience', 'mathematics', 'art']

    -- Evidence
    supporting_claims INTEGER[], -- References to claim IDs
    contradicting_claims INTEGER[],

    -- Significance
    significance TEXT,           -- 'major', 'moderate', 'minor'
    confidence REAL DEFAULT 0.5,

    -- Meta
    discovered_at TIMESTAMP DEFAULT NOW(),
    notes TEXT
);

-- GAPS: What we don't know yet
CREATE TABLE IF NOT EXISTS synthesis.knowledge_gaps (
    id SERIAL PRIMARY KEY,

    -- The gap
    question TEXT NOT NULL,      -- What we don't know
    field TEXT,
    subfield TEXT,

    -- Why it matters
    importance TEXT,
    potential_impact TEXT,

    -- Status
    status TEXT DEFAULT 'open', -- 'open', 'being_researched', 'partially_answered', 'closed'

    -- Related
    related_claims INTEGER[],
    related_patterns INTEGER[],

    created_at TIMESTAMP DEFAULT NOW()
);

-- AUTHORS: Who they are, what they do
CREATE TABLE IF NOT EXISTS synthesis.authors (
    id SERIAL PRIMARY KEY,

    name TEXT NOT NULL,
    orcid TEXT,

    -- Affiliations
    institutions TEXT[],
    countries TEXT[],

    -- Research profile
    primary_field TEXT,
    claim_count INTEGER DEFAULT 0,
    citation_count INTEGER DEFAULT 0,

    -- Investigation relevance
    epstein_connection BOOLEAN DEFAULT FALSE,
    connection_type TEXT,        -- 'direct', 'funding', 'collaboration', 'institution'
    investigation_notes TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- FUNDERS: Who pays for what
CREATE TABLE IF NOT EXISTS synthesis.funders (
    id SERIAL PRIMARY KEY,

    name TEXT NOT NULL,
    aliases TEXT[],              -- Other names used

    -- Profile
    country TEXT,
    funder_type TEXT,            -- 'government', 'private', 'foundation', 'anonymous'

    -- Stats
    papers_funded INTEGER DEFAULT 0,
    total_grants INTEGER DEFAULT 0,

    -- Investigation relevance
    epstein_connected BOOLEAN DEFAULT FALSE,
    suspicion_level TEXT,        -- 'clean', 'suspicious', 'confirmed_dirty'
    investigation_notes TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_claims_field ON synthesis.claims(field);
CREATE INDEX IF NOT EXISTS idx_claims_doi ON synthesis.claims(doi);
CREATE INDEX IF NOT EXISTS idx_claims_year ON synthesis.claims(source_year);
CREATE INDEX IF NOT EXISTS idx_claims_epstein ON synthesis.claims(epstein_relevant) WHERE epstein_relevant = TRUE;

CREATE INDEX IF NOT EXISTS idx_connections_type ON synthesis.connections(connection_type);
CREATE INDEX IF NOT EXISTS idx_connections_epstein ON synthesis.connections(epstein_score) WHERE epstein_score > 0;

CREATE INDEX IF NOT EXISTS idx_patterns_domains ON synthesis.patterns USING GIN(domains);

CREATE INDEX IF NOT EXISTS idx_authors_name ON synthesis.authors(name);
CREATE INDEX IF NOT EXISTS idx_authors_epstein ON synthesis.authors(epstein_connection);

CREATE INDEX IF NOT EXISTS idx_funders_name ON synthesis.funders(name);
CREATE INDEX IF NOT EXISTS idx_funders_epstein ON synthesis.funders(epstein_connected);

-- Full-text search on claims
CREATE INDEX IF NOT EXISTS idx_claims_fts ON synthesis.claims
    USING GIN(to_tsvector('english', claim));

-- Full-text search on patterns
CREATE INDEX IF NOT EXISTS idx_patterns_fts ON synthesis.patterns
    USING GIN(to_tsvector('english', pattern_name || ' ' || description));

-- Insert known Epstein-connected entities
INSERT INTO synthesis.funders (name, aliases, funder_type, epstein_connected, suspicion_level, investigation_notes)
VALUES
    ('Jeffrey Epstein', ARRAY['J. Epstein', 'Epstein'], 'private', TRUE, 'confirmed_dirty', 'Primary target'),
    ('Jeffrey Epstein VI Foundation', ARRAY['Epstein Foundation', 'JEPF'], 'foundation', TRUE, 'confirmed_dirty', 'Epstein foundation'),
    ('Gratitude America Ltd', ARRAY['Gratitude America'], 'private', TRUE, 'confirmed_dirty', 'Epstein shell entity'),
    ('Anonymous Donor to MIT Media Lab', ARRAY['Anonymous'], 'private', TRUE, 'suspicious', 'Likely Epstein money laundering')
ON CONFLICT DO NOTHING;

INSERT INTO synthesis.authors (name, institutions, primary_field, epstein_connection, connection_type, investigation_notes)
VALUES
    ('Joi Ito', ARRAY['MIT Media Lab'], 'technology', TRUE, 'direct', 'Accepted Epstein funding, resigned'),
    ('Martin Nowak', ARRAY['Harvard University', 'Program for Evolutionary Dynamics'], 'evolutionary biology', TRUE, 'funding', 'Major Epstein funding recipient'),
    ('Marvin Minsky', ARRAY['MIT'], 'artificial intelligence', TRUE, 'direct', 'Named in victim testimony'),
    ('George Church', ARRAY['Harvard', 'MIT'], 'genetics', TRUE, 'funding', 'Met with Epstein, discussed genetics')
ON CONFLICT DO NOTHING;

COMMENT ON SCHEMA synthesis IS 'Cognitive synthesis - storing understanding, not data';
COMMENT ON TABLE synthesis.claims IS 'What is claimed to be known - the building blocks of knowledge';
COMMENT ON TABLE synthesis.contradictions IS 'When claims conflict - the edges of our understanding';
COMMENT ON TABLE synthesis.connections IS 'Who influences who - the hidden network of science';
COMMENT ON TABLE synthesis.patterns IS 'Cross-domain discoveries - what silos hide';
COMMENT ON TABLE synthesis.knowledge_gaps IS 'What we dont know yet - the frontier';
