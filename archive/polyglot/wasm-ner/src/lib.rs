//! L Investigation - WebAssembly Entity Highlighter
//!
//! Near-native performance entity highlighting in the browser
//! Compiled from Rust to WASM

use lazy_static::lazy_static;
use regex::Regex;
use serde::{Deserialize, Serialize};
use wasm_bindgen::prelude::*;

// =============================================================================
// DATA STRUCTURES
// =============================================================================

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HighlightedEntity {
    pub text: String,
    pub entity_type: String,
    pub start: usize,
    pub end: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HighlightResult {
    pub html: String,
    pub entities: Vec<HighlightedEntity>,
    pub count: usize,
}

// =============================================================================
// REGEX PATTERNS
// =============================================================================

lazy_static! {
    // Person names
    static ref PERSON_RE: Regex = Regex::new(
        r"\b([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)\b"
    ).unwrap();

    // Organizations
    static ref ORG_RE: Regex = Regex::new(
        r"\b([A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+(?:Inc|Corp|LLC|Ltd|Foundation|Institute|Bank|Trust)\.?)\b"
    ).unwrap();

    // Money amounts
    static ref AMOUNT_RE: Regex = Regex::new(
        r"(\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:million|billion|M|B))?)"
    ).unwrap();

    // Dates
    static ref DATE_RE: Regex = Regex::new(
        r"\b(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s*\d{4})\b"
    ).unwrap();

    // Locations
    static ref LOCATION_RE: Regex = Regex::new(
        r"\b(New York|Los Angeles|London|Paris|Miami|Washington|Virgin Islands|Palm Beach|Manhattan|Florida|California)\b"
    ).unwrap();

    // Emails
    static ref EMAIL_RE: Regex = Regex::new(
        r"\b([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b"
    ).unwrap();
}

// =============================================================================
// HIGHLIGHTING FUNCTIONS
// =============================================================================

fn escape_html(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

fn highlight_matches(text: &str, regex: &Regex, entity_type: &str, class: &str) -> (String, Vec<HighlightedEntity>) {
    let mut entities = Vec::new();
    let mut result = String::new();
    let mut last_end = 0;

    for cap in regex.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            // Add text before match
            result.push_str(&escape_html(&text[last_end..m.start()]));

            // Add highlighted match
            let matched = m.as_str();
            result.push_str(&format!(
                r#"<span class="entity {}" data-type="{}">{}</span>"#,
                class,
                entity_type,
                escape_html(matched)
            ));

            entities.push(HighlightedEntity {
                text: matched.to_string(),
                entity_type: entity_type.to_string(),
                start: m.start(),
                end: m.end(),
            });

            last_end = m.end();
        }
    }

    result.push_str(&escape_html(&text[last_end..]));
    (result, entities)
}

// =============================================================================
// WASM EXPORTS
// =============================================================================

/// Highlight all entities in text, returning HTML with spans
#[wasm_bindgen]
pub fn highlight_entities(text: &str) -> JsValue {
    let mut all_entities: Vec<(usize, usize, String, String, String)> = Vec::new();

    // Collect all matches with their positions
    for cap in PERSON_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            all_entities.push((m.start(), m.end(), m.as_str().to_string(), "person".to_string(), "entity-person".to_string()));
        }
    }

    for cap in ORG_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            all_entities.push((m.start(), m.end(), m.as_str().to_string(), "organization".to_string(), "entity-org".to_string()));
        }
    }

    for cap in AMOUNT_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            all_entities.push((m.start(), m.end(), m.as_str().to_string(), "amount".to_string(), "entity-amount".to_string()));
        }
    }

    for cap in DATE_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            all_entities.push((m.start(), m.end(), m.as_str().to_string(), "date".to_string(), "entity-date".to_string()));
        }
    }

    for cap in LOCATION_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            all_entities.push((m.start(), m.end(), m.as_str().to_string(), "location".to_string(), "entity-location".to_string()));
        }
    }

    for cap in EMAIL_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            all_entities.push((m.start(), m.end(), m.as_str().to_string(), "email".to_string(), "entity-email".to_string()));
        }
    }

    // Sort by start position
    all_entities.sort_by_key(|e| e.0);

    // Remove overlapping entities (keep first)
    let mut filtered: Vec<(usize, usize, String, String, String)> = Vec::new();
    let mut last_end = 0;
    for entity in all_entities {
        if entity.0 >= last_end {
            last_end = entity.1;
            filtered.push(entity);
        }
    }

    // Build HTML
    let mut html = String::new();
    let mut last_pos = 0;
    let mut entities_out = Vec::new();

    for (start, end, matched, entity_type, class) in &filtered {
        html.push_str(&escape_html(&text[last_pos..*start]));
        html.push_str(&format!(
            r#"<span class="entity {}" data-type="{}" title="{}">{}</span>"#,
            class,
            entity_type,
            entity_type,
            escape_html(matched)
        ));
        entities_out.push(HighlightedEntity {
            text: matched.clone(),
            entity_type: entity_type.clone(),
            start: *start,
            end: *end,
        });
        last_pos = *end;
    }
    html.push_str(&escape_html(&text[last_pos..]));

    let result = HighlightResult {
        html,
        entities: entities_out.clone(),
        count: entities_out.len(),
    };

    serde_wasm_bindgen::to_value(&result).unwrap()
}

/// Extract entities without highlighting
#[wasm_bindgen]
pub fn extract_entities(text: &str) -> JsValue {
    let mut entities = Vec::new();

    for cap in PERSON_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            entities.push(HighlightedEntity {
                text: m.as_str().to_string(),
                entity_type: "person".to_string(),
                start: m.start(),
                end: m.end(),
            });
        }
    }

    for cap in ORG_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            entities.push(HighlightedEntity {
                text: m.as_str().to_string(),
                entity_type: "organization".to_string(),
                start: m.start(),
                end: m.end(),
            });
        }
    }

    for cap in AMOUNT_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            entities.push(HighlightedEntity {
                text: m.as_str().to_string(),
                entity_type: "amount".to_string(),
                start: m.start(),
                end: m.end(),
            });
        }
    }

    for cap in DATE_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            entities.push(HighlightedEntity {
                text: m.as_str().to_string(),
                entity_type: "date".to_string(),
                start: m.start(),
                end: m.end(),
            });
        }
    }

    for cap in LOCATION_RE.captures_iter(text) {
        if let Some(m) = cap.get(1) {
            entities.push(HighlightedEntity {
                text: m.as_str().to_string(),
                entity_type: "location".to_string(),
                start: m.start(),
                end: m.end(),
            });
        }
    }

    serde_wasm_bindgen::to_value(&entities).unwrap()
}

/// Count entities by type
#[wasm_bindgen]
pub fn count_entities(text: &str) -> JsValue {
    let counts = serde_json::json!({
        "persons": PERSON_RE.captures_iter(text).count(),
        "organizations": ORG_RE.captures_iter(text).count(),
        "amounts": AMOUNT_RE.captures_iter(text).count(),
        "dates": DATE_RE.captures_iter(text).count(),
        "locations": LOCATION_RE.captures_iter(text).count(),
        "emails": EMAIL_RE.captures_iter(text).count(),
    });

    serde_wasm_bindgen::to_value(&counts).unwrap()
}

// =============================================================================
// INIT
// =============================================================================

#[wasm_bindgen(start)]
pub fn main() {
    // Initialize panic hook for better error messages
    #[cfg(feature = "console_error_panic_hook")]
    console_error_panic_hook::set_once();
}
