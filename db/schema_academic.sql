-- Schema for Academic Papers Ingestion
-- Part of the Sci-Hub/OpenAlex/arXiv integration
-- Created: 2026-01-10

-- Create schema
CREATE SCHEMA IF NOT EXISTS academic;

-- Main papers table
CREATE TABLE IF NOT EXISTS academic.papers (
    id SERIAL PRIMARY KEY,

    -- Identifiers
    doi TEXT UNIQUE,
    openalex_id TEXT,
    semantic_id TEXT,
    arxiv_id TEXT,
    pmid TEXT,
    pmcid TEXT,

    -- Core metadata
    title TEXT NOT NULL,
    abstract TEXT,
    publication_date DATE,
    year INTEGER,

    -- Source
    journal TEXT,
    publisher TEXT,
    source_type TEXT,  -- 'journal', 'preprint', 'book', 'conference'

    -- Authors (JSONB array)
    authors JSONB DEFAULT '[]',
    -- [{name, orcid, affiliation, affiliation_id, position}]

    -- Affiliations (JSONB array)
    institutions JSONB DEFAULT '[]',
    -- [{id, name, country, type}]

    -- Funding (JSONB array)
    funders JSONB DEFAULT '[]',
    -- [{id, name, award_id, country}]

    -- Topics/Subjects
    topics JSONB DEFAULT '[]',
    -- [{id, name, field, subfield}]
    fields TEXT[],  -- e.g., ['Mathematics', 'Neuroscience']

    -- Metrics
    citation_count INTEGER DEFAULT 0,
    reference_count INTEGER DEFAULT 0,

    -- Open Access
    is_open_access BOOLEAN DEFAULT FALSE,
    oa_status TEXT,  -- 'gold', 'green', 'hybrid', 'bronze', 'closed'
    oa_url TEXT,

    -- Full text
    has_full_text BOOLEAN DEFAULT FALSE,
    full_text TEXT,
    pdf_path TEXT,

    -- Processing status
    source TEXT,  -- 'openalex', 'arxiv', 'pmc', 'semantic', 'scihub'
    ingested_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP,

    -- For investigation
    epstein_relevant BOOLEAN DEFAULT FALSE,
    relevance_score REAL DEFAULT 0.0,
    investigation_notes TEXT
);

-- Authors table for better querying
CREATE TABLE IF NOT EXISTS academic.authors (
    id SERIAL PRIMARY KEY,
    openalex_id TEXT UNIQUE,
    orcid TEXT,
    name TEXT NOT NULL,
    display_name TEXT,

    -- Affiliations history
    affiliations JSONB DEFAULT '[]',

    -- Metrics
    works_count INTEGER DEFAULT 0,
    citation_count INTEGER DEFAULT 0,
    h_index INTEGER,

    -- Investigation links
    entity_id INTEGER,  -- Link to graph.nodes if matched

    created_at TIMESTAMP DEFAULT NOW()
);

-- Paper-Author junction
CREATE TABLE IF NOT EXISTS academic.paper_authors (
    paper_id INTEGER REFERENCES academic.papers(id) ON DELETE CASCADE,
    author_id INTEGER REFERENCES academic.authors(id) ON DELETE CASCADE,
    position INTEGER,  -- 1 = first author, -1 = last author
    is_corresponding BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (paper_id, author_id)
);

-- Institutions table
CREATE TABLE IF NOT EXISTS academic.institutions (
    id SERIAL PRIMARY KEY,
    openalex_id TEXT UNIQUE,
    ror_id TEXT,
    name TEXT NOT NULL,
    display_name TEXT,
    country TEXT,
    country_code TEXT,
    type TEXT,  -- 'university', 'company', 'government', 'nonprofit'

    -- Investigation flags
    epstein_connected BOOLEAN DEFAULT FALSE,
    investigation_notes TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- Funders table
CREATE TABLE IF NOT EXISTS academic.funders (
    id SERIAL PRIMARY KEY,
    openalex_id TEXT UNIQUE,
    crossref_id TEXT,
    name TEXT NOT NULL,
    display_name TEXT,
    country TEXT,

    -- Investigation flags
    epstein_connected BOOLEAN DEFAULT FALSE,
    investigation_notes TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- Cross-reference with investigation graph
CREATE TABLE IF NOT EXISTS academic.entity_links (
    id SERIAL PRIMARY KEY,

    -- Academic side
    paper_id INTEGER REFERENCES academic.papers(id),
    author_id INTEGER REFERENCES academic.authors(id),
    institution_id INTEGER REFERENCES academic.institutions(id),
    funder_id INTEGER REFERENCES academic.funders(id),

    -- Investigation side
    entity_id INTEGER,  -- Link to graph.nodes
    entity_name TEXT,
    entity_type TEXT,

    -- Link metadata
    link_type TEXT,  -- 'same_person', 'funded_by', 'worked_at', 'mentioned'
    confidence REAL DEFAULT 1.0,
    evidence TEXT,

    created_at TIMESTAMP DEFAULT NOW()
);

-- Ingestion jobs tracking
CREATE TABLE IF NOT EXISTS academic.ingestion_jobs (
    id SERIAL PRIMARY KEY,
    job_type TEXT,  -- 'openalex', 'arxiv', 'pmc', 'scihub'
    query TEXT,
    status TEXT DEFAULT 'pending',  -- 'pending', 'running', 'completed', 'failed'

    papers_found INTEGER DEFAULT 0,
    papers_ingested INTEGER DEFAULT 0,
    papers_failed INTEGER DEFAULT 0,

    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_papers_doi ON academic.papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_year ON academic.papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_fields ON academic.papers USING GIN(fields);
CREATE INDEX IF NOT EXISTS idx_papers_topics ON academic.papers USING GIN(topics);
CREATE INDEX IF NOT EXISTS idx_papers_funders ON academic.papers USING GIN(funders);
CREATE INDEX IF NOT EXISTS idx_papers_authors ON academic.papers USING GIN(authors);
CREATE INDEX IF NOT EXISTS idx_papers_epstein ON academic.papers(epstein_relevant) WHERE epstein_relevant = TRUE;
CREATE INDEX IF NOT EXISTS idx_papers_oa ON academic.papers(is_open_access) WHERE is_open_access = TRUE;

CREATE INDEX IF NOT EXISTS idx_authors_name ON academic.authors(name);
CREATE INDEX IF NOT EXISTS idx_authors_orcid ON academic.authors(orcid);
CREATE INDEX IF NOT EXISTS idx_authors_entity ON academic.authors(entity_id);

CREATE INDEX IF NOT EXISTS idx_institutions_name ON academic.institutions(name);
CREATE INDEX IF NOT EXISTS idx_institutions_epstein ON academic.institutions(epstein_connected);

CREATE INDEX IF NOT EXISTS idx_funders_name ON academic.funders(name);
CREATE INDEX IF NOT EXISTS idx_funders_epstein ON academic.funders(epstein_connected);

-- Full-text search on papers
CREATE INDEX IF NOT EXISTS idx_papers_fts ON academic.papers
    USING GIN(to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(abstract, '')));

-- Full-text search including full text content
CREATE INDEX IF NOT EXISTS idx_papers_fulltext_fts ON academic.papers
    USING GIN(to_tsvector('english', COALESCE(full_text, '')))
    WHERE full_text IS NOT NULL;

-- Priority institutions for Epstein investigation
INSERT INTO academic.institutions (name, display_name, type, epstein_connected, investigation_notes)
VALUES
    ('MIT Media Lab', 'MIT Media Lab', 'university', TRUE, 'Joi Ito accepted Epstein funding'),
    ('Harvard University', 'Harvard University', 'university', TRUE, 'Multiple Epstein donations'),
    ('Program for Evolutionary Dynamics', 'Harvard PED', 'university', TRUE, 'Martin Nowak, major Epstein funding'),
    ('Santa Fe Institute', 'Santa Fe Institute', 'nonprofit', TRUE, 'Epstein was on the board')
ON CONFLICT (openalex_id) DO NOTHING;

-- Priority funders for investigation
INSERT INTO academic.funders (name, display_name, epstein_connected, investigation_notes)
VALUES
    ('Jeffrey Epstein', 'Jeffrey Epstein', TRUE, 'Primary target'),
    ('Epstein Foundation', 'Jeffrey Epstein VI Foundation', TRUE, 'Epstein''s foundation'),
    ('JEPF', 'J. Epstein Foundation', TRUE, 'Alternate name'),
    ('Gratitude America', 'Gratitude America Ltd', TRUE, 'Epstein shell entity')
ON CONFLICT (openalex_id) DO NOTHING;

COMMENT ON TABLE academic.papers IS 'Academic papers from OpenAlex, arXiv, PMC, Semantic Scholar, Sci-Hub';
COMMENT ON TABLE academic.authors IS 'Disambiguated authors with links to investigation entities';
COMMENT ON TABLE academic.institutions IS 'Research institutions with Epstein connection flags';
COMMENT ON TABLE academic.funders IS 'Funding sources with Epstein connection flags';
COMMENT ON TABLE academic.entity_links IS 'Cross-references between academic entities and investigation graph';
