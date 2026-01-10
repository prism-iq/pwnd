//! L Investigation - Rust Extraction HTTP Server
//!
//! High-performance entity extraction API
//! Port: 9001

use actix_web::{web, App, HttpResponse, HttpServer, middleware};
use serde::{Deserialize, Serialize};
use l_extract::{extract_all, extract_types, extract_batch, ExtractionResult};

#[derive(Deserialize)]
struct ExtractRequest {
    text: String,
    #[serde(default)]
    types: Option<Vec<String>>,
}

#[derive(Deserialize)]
struct BatchRequest {
    documents: Vec<String>,
}

#[derive(Serialize)]
struct HealthResponse {
    status: &'static str,
    service: &'static str,
    version: &'static str,
}

#[derive(Serialize)]
struct StatsResponse {
    status: &'static str,
    threads: usize,
    version: &'static str,
}

// Health check
async fn health() -> HttpResponse {
    HttpResponse::Ok().json(HealthResponse {
        status: "healthy",
        service: "l-extract-rust",
        version: "1.0.0",
    })
}

// Stats
async fn stats() -> HttpResponse {
    HttpResponse::Ok().json(StatsResponse {
        status: "ready",
        threads: rayon::current_num_threads(),
        version: "1.0.0",
    })
}

// Extract entities from single document
async fn extract(req: web::Json<ExtractRequest>) -> HttpResponse {
    let result = if let Some(ref types) = req.types {
        let type_refs: Vec<&str> = types.iter().map(|s| s.as_str()).collect();
        extract_types(&req.text, &type_refs)
    } else {
        extract_all(&req.text)
    };

    HttpResponse::Ok().json(result)
}

// Batch extraction
async fn batch(req: web::Json<BatchRequest>) -> HttpResponse {
    let doc_refs: Vec<&str> = req.documents.iter().map(|s| s.as_str()).collect();
    let results = extract_batch(&doc_refs);
    HttpResponse::Ok().json(results)
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    // Initialize logging
    tracing_subscriber::fmt::init();

    let port = std::env::var("PORT").unwrap_or_else(|_| "9001".to_string());
    let addr = format!("127.0.0.1:{}", port);

    println!(r#"
╔═══════════════════════════════════════════════════════════╗
║       L Investigation - Rust Extraction Engine            ║
║       Parallel regex, 10x faster than Python              ║
╠═══════════════════════════════════════════════════════════╣
║  Endpoints:                                               ║
║    POST /extract      - Extract from single document      ║
║    POST /batch        - Extract from multiple documents   ║
║    GET  /health       - Health check                      ║
║    GET  /stats        - Server statistics                 ║
╚═══════════════════════════════════════════════════════════╝
    "#);

    println!("Starting server on {}", addr);
    println!("Rayon threads: {}", rayon::current_num_threads());

    HttpServer::new(|| {
        App::new()
            .wrap(middleware::Logger::default())
            .wrap(middleware::Compress::default())
            .route("/health", web::get().to(health))
            .route("/stats", web::get().to(stats))
            .route("/extract", web::post().to(extract))
            .route("/batch", web::post().to(batch))
    })
    .bind(&addr)?
    .run()
    .await
}
