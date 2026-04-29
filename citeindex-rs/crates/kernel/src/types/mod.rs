//! Type contracts for the CiteIndex v12 kernel.
//!
//! These types enforce the five formal invariants (I1–I5) at compile time
//! (typestate) and runtime. They are the foundation that every other module
//! depends on.
//!
//! Layout matches `T_type_contracts.md`.

pub mod admission;
pub mod claim;
pub mod commit;
pub mod common;
pub mod context_slot;
pub mod frame;
pub mod ids;
pub mod interrupt;
pub mod query_plan;
pub mod recovery;
pub mod replay;
pub mod state;
pub mod structure;
pub mod transitions;
pub mod tree;

// Re-export all public types at the `types` level.
pub use admission::*;
pub use claim::*;
pub use commit::*;
pub use common::*;
pub use context_slot::*;
pub use frame::*;
pub use ids::*;
pub use interrupt::*;
pub use query_plan::*;
pub use recovery::*;
pub use replay::*;
pub use state::*;
pub use structure::*;
pub use transitions::*;
pub use tree::*;
