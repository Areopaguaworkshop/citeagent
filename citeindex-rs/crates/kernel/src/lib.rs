//! CiteIndex v12 Kernel — DKEE state machine, type contracts, tool dispatcher.
//!
//! This crate implements the Rust kernel layer of the CiteIndex Harness OS.
//! The kernel owns the state machine and enforces invariants I1–I5 at compile
//! time (typestate) and runtime. It never calls an LLM directly.

pub mod ace;
pub mod agent_runtime;
pub mod api;
pub mod argument_graph;
pub mod cli;
pub mod config;
pub mod context;
pub mod gate;
pub mod indexes;
pub mod lora;
pub mod migration;
pub mod recovery;
pub mod retrieval;
pub mod scoring;
pub mod skillpack;
pub mod state_machine;
pub mod storage;
pub mod tools;
pub mod trace;
pub mod types;
