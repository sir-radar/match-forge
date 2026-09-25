//! Deterministic categorical simulation for the frozen PitchAPI V2 policy.
#![forbid(unsafe_code)]

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use statrs::distribution::{Beta, ContinuousCDF};
use std::collections::{BTreeMap, BTreeSet};
use std::fmt::{Display, Formatter};
use std::thread;

pub const PROTOCOL_ID: &str = "PITCHAPI_DOMAIN_STRATIFIED_EVALUATION_V2";
pub const POLICY_SHA256: &str = "8154e8b78b307dd25e7167ad00f2a310f012b1474580a82795e72acd5ce3a9ee";
pub const ALGORITHM_VERSION: &str = "pitchapi-score-categorical-v1";
pub const SEED_SCHEDULE_ID: &str = "pitchapi-v2-splitmix64-sha256-v1";
pub const SIMULATION_COUNT: u64 = 112_460;
pub const BATCH_COUNT: u32 = 4;
pub const DRAWS_PER_BATCH: u64 = 28_115;
const EVENT_COUNT: usize = 62;
const NORMALIZATION_TOLERANCE: f64 = 1e-12;
const STABILITY_LIMIT: f64 = 0.019_974_384_468_264_498;

#[derive(Debug, Clone, Eq, PartialEq)]
pub struct SimulationError {
    pub code: &'static str,
    pub message: String,
}
impl SimulationError {
    fn new(code: &'static str, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }
}
impl Display for SimulationError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.code, self.message)
    }
}
impl std::error::Error for SimulationError {}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, Eq, PartialEq)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum AtomKindV1 {
    ExactScore,
    UnresolvedTail,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct ScoreAtomV1 {
    pub away_goals: Option<u16>,
    pub home_goals: Option<u16>,
    pub kind: AtomKindV1,
    pub probability: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct AnalyticProbabilityV1 {
    pub event_id: String,
    pub probability: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
#[serde(deny_unknown_fields)]
pub struct SimulationInputV1 {
    pub algorithm_version: String,
    pub analytic_probabilities: Vec<AnalyticProbabilityV1>,
    pub atoms: Vec<ScoreAtomV1>,
    pub canonical_match_id: String,
    pub forecast_artifact_sha256: String,
    pub forecast_id: String,
    pub forecast_probability_sha256: String,
    pub model_artifact_sha256: String,
    pub policy_sha256: String,
    pub protocol_id: String,
    pub schema_version: String,
    pub seed_schedule_id: String,
    pub simulation_count: u64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct IntervalV1 {
    pub lower: f64,
    pub upper: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct EventValidationV1 {
    pub analytic_probability: f64,
    pub batch_counts: Vec<u64>,
    pub count: u64,
    pub event_id: String,
    pub parity_interval_99_familywise: IntervalV1,
    pub precision_half_width: f64,
    pub precision_interval_95_familywise: IntervalV1,
    pub simulated_probability: f64,
}

#[derive(Clone, Debug, Deserialize, Serialize, PartialEq)]
pub struct SimulationOutputV1 {
    pub algorithm_version: String,
    pub base_seed_commitment: String,
    pub batch_seed_ids: Vec<String>,
    pub events: Vec<EventValidationV1>,
    pub forecast_artifact_sha256: String,
    pub forecast_id: String,
    pub forecast_probability_sha256: String,
    pub input_sha256: String,
    pub policy_sha256: String,
    pub protocol_id: String,
    pub schema_version: String,
    pub seed_schedule_id: String,
    pub simulation_count: u64,
    pub stability_limit: f64,
    pub status: String,
    pub tail_draws: u64,
}
impl SimulationOutputV1 {
    pub fn canonical_bytes(&self) -> Result<Vec<u8>, SimulationError> {
        canonical_serialize(self)
    }
    pub fn sha256(&self) -> Result<String, SimulationError> {
        Ok(sha256_hex(&self.canonical_bytes()?))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct SplitMix64 {
    state: u64,
}
impl SplitMix64 {
    #[must_use]
    pub const fn new(seed: u64) -> Self {
        Self { state: seed }
    }
    #[must_use]
    pub fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        z ^ (z >> 31)
    }
    #[must_use]
    pub fn next_unit_f64(&mut self) -> f64 {
        (((self.next_u64() >> 11) as f64) + 0.5) / ((1_u64 << 53) as f64)
    }
}

pub fn parse_canonical_input(
    payload: &[u8],
    expected_sha256: &str,
) -> Result<SimulationInputV1, SimulationError> {
    if sha256_hex(payload) != expected_sha256 {
        return Err(err(
            "INPUT_HASH_MISMATCH",
            "input bytes do not match expected SHA-256",
        ));
    }
    let value: Value =
        serde_json::from_slice(payload).map_err(|e| err("MALFORMED_INPUT", e.to_string()))?;
    let canonical = serde_json::to_vec(&sort_json(value.clone()))
        .map_err(|e| err("MALFORMED_INPUT", e.to_string()))?;
    if canonical != payload {
        return Err(err(
            "NON_CANONICAL_INPUT",
            "input must use sorted keys without insignificant whitespace",
        ));
    }
    let input = serde_json::from_value(value).map_err(|e| err("MALFORMED_INPUT", e.to_string()))?;
    validate_input(&input)?;
    Ok(input)
}

pub fn run(
    input: &SimulationInputV1,
    input_sha256: &str,
    workers: usize,
) -> Result<SimulationOutputV1, SimulationError> {
    validate_input(input)?;
    if !(1..=4).contains(&workers) {
        return Err(err(
            "INVALID_WORKER_COUNT",
            "worker count must be between one and four",
        ));
    }
    let ids = event_ids();
    let analytic: BTreeMap<&str, f64> = input
        .analytic_probabilities
        .iter()
        .map(|p| (p.event_id.as_str(), p.probability))
        .collect();
    let base = base_seed_commitment(&input.forecast_probability_sha256);
    let seeds: Vec<[u8; 32]> = (0..BATCH_COUNT)
        .map(|i| batch_seed(&base, &input.canonical_match_id, i))
        .collect();
    let mut batches = vec![vec![0_u64; EVENT_COUNT]; BATCH_COUNT as usize];
    let mut tails = vec![0_u64; BATCH_COUNT as usize];
    if workers == 1 {
        for i in 0..BATCH_COUNT as usize {
            (batches[i], tails[i]) = run_batch(&input.atoms, seeds[i])?;
        }
    } else {
        thread::scope(|scope| -> Result<(), SimulationError> {
            let handles: Vec<_> = seeds
                .iter()
                .copied()
                .map(|seed| scope.spawn(move || run_batch(&input.atoms, seed)))
                .collect();
            for (i, handle) in handles.into_iter().enumerate() {
                (batches[i], tails[i]) = handle
                    .join()
                    .map_err(|_| err("WORKER_FAILURE", "worker panicked"))??;
            }
            Ok(())
        })?;
    }
    let tail_draws = tails.iter().sum();
    if tail_draws != 0 {
        return Err(err(
            "UNRESOLVED_TAIL_SAMPLED",
            format!("sampled unresolved tail {tail_draws} times"),
        ));
    }
    let mut events = Vec::with_capacity(EVENT_COUNT);
    for (index, event_id) in ids.iter().enumerate() {
        let batch_counts: Vec<u64> = batches.iter().map(|batch| batch[index]).collect();
        validate_stability(event_id, &batch_counts)?;
        let count = batch_counts.iter().sum();
        let precision = clopper_pearson(count, SIMULATION_COUNT, 0.05 / 62.0)?;
        let parity = clopper_pearson(count, SIMULATION_COUNT, 0.01 / 62.0)?;
        let half = (precision.upper - precision.lower) / 2.0;
        if half > 0.005 {
            return Err(err(
                "PRECISION_FAILURE",
                format!("{event_id} half-width {half} exceeds 0.005"),
            ));
        }
        let probability = analytic[event_id.as_str()];
        if probability < parity.lower || probability > parity.upper {
            return Err(err(
                "PARITY_FAILURE",
                format!("{event_id} analytic probability is outside parity interval"),
            ));
        }
        events.push(EventValidationV1 {
            analytic_probability: probability,
            batch_counts,
            count,
            event_id: event_id.clone(),
            parity_interval_99_familywise: parity,
            precision_half_width: half,
            precision_interval_95_familywise: precision,
            simulated_probability: count as f64 / SIMULATION_COUNT as f64,
        });
    }
    Ok(SimulationOutputV1 {
        algorithm_version: ALGORITHM_VERSION.into(),
        base_seed_commitment: hex_bytes(&base),
        batch_seed_ids: seeds.iter().map(|s| hex_bytes(s)).collect(),
        events,
        forecast_artifact_sha256: input.forecast_artifact_sha256.clone(),
        forecast_id: input.forecast_id.clone(),
        forecast_probability_sha256: input.forecast_probability_sha256.clone(),
        input_sha256: input_sha256.into(),
        policy_sha256: POLICY_SHA256.into(),
        protocol_id: PROTOCOL_ID.into(),
        schema_version: "SimulationValidationArtifactV1".into(),
        seed_schedule_id: SEED_SCHEDULE_ID.into(),
        simulation_count: SIMULATION_COUNT,
        stability_limit: STABILITY_LIMIT,
        status: "PASS".into(),
        tail_draws,
    })
}

pub fn analytic_probabilities(atoms: &[ScoreAtomV1]) -> Vec<AnalyticProbabilityV1> {
    let mut totals = vec![0.0; EVENT_COUNT];
    for atom in atoms {
        if atom.kind == AtomKindV1::UnresolvedTail {
            totals[61] += atom.probability;
        } else if let Some((home, away)) = atom.home_goals.zip(atom.away_goals) {
            for i in event_indexes(home, away) {
                totals[i] += atom.probability;
            }
        }
    }
    event_ids()
        .into_iter()
        .zip(totals)
        .map(|(event_id, probability)| AnalyticProbabilityV1 {
            event_id,
            probability,
        })
        .collect()
}

pub fn canonical_bytes<T: Serialize>(value: &T) -> Result<Vec<u8>, SimulationError> {
    canonical_serialize(value)
}
pub fn sha256(payload: &[u8]) -> String {
    sha256_hex(payload)
}

pub fn benchmark_synthetic_targets(
    target_count: usize,
    workers: usize,
) -> Result<(u64, u64), SimulationError> {
    if target_count == 0 || !(1..=4).contains(&workers) {
        return Err(err(
            "INVALID_BENCHMARK",
            "targets and workers must be positive and workers <= 4",
        ));
    }
    let atoms = [
        ScoreAtomV1 {
            away_goals: Some(0),
            home_goals: Some(0),
            kind: AtomKindV1::ExactScore,
            probability: 0.5,
        },
        ScoreAtomV1 {
            away_goals: Some(0),
            home_goals: Some(1),
            kind: AtomKindV1::ExactScore,
            probability: 0.5,
        },
        ScoreAtomV1 {
            away_goals: None,
            home_goals: None,
            kind: AtomKindV1::UnresolvedTail,
            probability: 0.0,
        },
    ];
    let base = base_seed_commitment(&"c".repeat(64));
    let checksum = thread::scope(|scope| -> Result<u64, SimulationError> {
        let mut handles = Vec::new();
        for worker in 0..workers {
            let atoms = &atoms;
            handles.push(scope.spawn(move || {
                let mut checksum = 0_u64;
                for target in (worker..target_count).step_by(workers) {
                    for batch in 0..BATCH_COUNT {
                        let seed = batch_seed(&base, &format!("synthetic-{target}"), batch);
                        let (counts, tails) = run_batch(atoms, seed)?;
                        checksum = checksum
                            .wrapping_add(counts.into_iter().sum::<u64>())
                            .wrapping_add(tails);
                    }
                }
                Ok(checksum)
            }));
        }
        let mut checksum = 0_u64;
        for handle in handles {
            checksum = checksum.wrapping_add(
                handle
                    .join()
                    .map_err(|_| err("WORKER_FAILURE", "benchmark worker panicked"))??,
            );
        }
        Ok(checksum)
    })?;
    Ok((target_count as u64 * SIMULATION_COUNT, checksum))
}

fn validate_input(input: &SimulationInputV1) -> Result<(), SimulationError> {
    if input.schema_version != "PitchApiSimulationInputV1"
        || input.protocol_id != PROTOCOL_ID
        || input.policy_sha256 != POLICY_SHA256
        || input.algorithm_version != ALGORITHM_VERSION
        || input.seed_schedule_id != SEED_SCHEDULE_ID
    {
        return Err(err(
            "UNSUPPORTED_IDENTITY",
            "input identities do not match frozen V2",
        ));
    }
    if input.simulation_count != SIMULATION_COUNT {
        return Err(err(
            "INVALID_SIMULATION_COUNT",
            format!("simulation_count must equal {SIMULATION_COUNT}"),
        ));
    }
    if input.canonical_match_id.is_empty() || input.forecast_id.is_empty() {
        return Err(err("MALFORMED_INPUT", "identifiers must not be empty"));
    }
    for value in [
        &input.forecast_artifact_sha256,
        &input.forecast_probability_sha256,
        &input.model_artifact_sha256,
    ] {
        validate_hash(value)?;
    }
    if input.atoms.len() < 2 {
        return Err(err("INVALID_ATOMS", "exact and tail atoms are required"));
    }
    let mut seen = BTreeSet::new();
    let mut previous = None;
    let mut sum = 0.0;
    for (i, atom) in input.atoms.iter().enumerate() {
        validate_probability(atom.probability)?;
        sum += atom.probability;
        match atom.kind {
            AtomKindV1::ExactScore => {
                let score = atom
                    .home_goals
                    .zip(atom.away_goals)
                    .ok_or_else(|| err("INVALID_ATOMS", "exact atom lacks goals"))?;
                if i == input.atoms.len() - 1
                    || previous.is_some_and(|p| score <= p)
                    || !seen.insert(score)
                {
                    return Err(err(
                        "INVALID_ATOMS",
                        "exact atoms must be unique and ordered",
                    ));
                }
                previous = Some(score);
            }
            AtomKindV1::UnresolvedTail => {
                if i != input.atoms.len() - 1
                    || atom.home_goals.is_some()
                    || atom.away_goals.is_some()
                    || atom.probability > NORMALIZATION_TOLERANCE
                {
                    return Err(err("INVALID_ATOMS", "bounded tail must be final"));
                }
            }
        }
    }
    if (sum - 1.0).abs() > NORMALIZATION_TOLERANCE {
        return Err(err(
            "INVALID_NORMALIZATION",
            format!("probabilities sum to {sum}"),
        ));
    }
    if sha256_hex(&canonical_serialize(&input.atoms)?) != input.forecast_probability_sha256 {
        return Err(err("PROBABILITY_HASH_MISMATCH", "atom hash mismatch"));
    }
    let ids = event_ids();
    if input.analytic_probabilities.len() != EVENT_COUNT {
        return Err(err(
            "INVALID_ANALYTIC_PROBABILITIES",
            "exactly 62 values required",
        ));
    }
    for (actual, expected) in input.analytic_probabilities.iter().zip(ids) {
        if actual.event_id != expected {
            return Err(err("INVALID_ANALYTIC_PROBABILITIES", "wrong event order"));
        }
        validate_probability(actual.probability)?;
    }
    Ok(())
}

fn run_batch(atoms: &[ScoreAtomV1], seed: [u8; 32]) -> Result<(Vec<u64>, u64), SimulationError> {
    let mut rng = SplitMix64::new(u64::from_be_bytes(
        seed[..8]
            .try_into()
            .map_err(|_| err("SEED_FAILURE", "invalid seed"))?,
    ));
    let mut counts = vec![0_u64; EVENT_COUNT];
    let mut tails = 0_u64;
    for _ in 0..DRAWS_PER_BATCH {
        let u = rng.next_unit_f64();
        let mut cdf = 0.0;
        let mut selected = None;
        for atom in atoms {
            cdf += atom.probability;
            if cdf > u {
                selected = Some(atom);
                break;
            }
        }
        let atom = selected.ok_or_else(|| err("CUMULATIVE_RANGE_FAILURE", "draw exceeded CDF"))?;
        if atom.kind == AtomKindV1::UnresolvedTail {
            tails += 1;
        } else {
            let (h, a) = atom
                .home_goals
                .zip(atom.away_goals)
                .ok_or_else(|| err("INVALID_ATOMS", "missing goals"))?;
            for i in event_indexes(h, a) {
                counts[i] = counts[i]
                    .checked_add(1)
                    .ok_or_else(|| err("ARITHMETIC_OVERFLOW", "count overflow"))?;
            }
        }
    }
    Ok((counts, tails))
}

fn event_indexes(home: u16, away: u16) -> Vec<usize> {
    let mut v = vec![
        usize::from(home.min(5)) * 6 + usize::from(away.min(5)),
        if home > away {
            36
        } else if home == away {
            37
        } else {
            38
        },
        if home > 0 && away > 0 { 39 } else { 40 },
    ];
    let total = home + away;
    for t in 0..5u16 {
        v.push(41 + usize::from(t) * 2 + usize::from(total <= t));
    }
    v.push(if away == 0 { 51 } else { 52 });
    v.push(if home == 0 { 53 } else { 54 });
    v.push(55 + usize::from(total.min(5)));
    v
}
fn event_ids() -> Vec<String> {
    let mut v = Vec::new();
    for h in ["0", "1", "2", "3", "4", "5+"] {
        for a in ["0", "1", "2", "3", "4", "5+"] {
            v.push(format!("score:{h}-{a}"));
        }
    }
    v.extend(
        [
            "outcome:home_win",
            "outcome:draw",
            "outcome:away_win",
            "btts:yes",
            "btts:no",
        ]
        .map(str::to_owned),
    );
    for t in ["0.5", "1.5", "2.5", "3.5", "4.5"] {
        v.push(format!("total:over_{t}"));
        v.push(format!("total:under_{t}"));
    }
    v.extend(
        [
            "clean_sheet:home_yes",
            "clean_sheet:home_no",
            "clean_sheet:away_yes",
            "clean_sheet:away_no",
            "total_goals:0",
            "total_goals:1",
            "total_goals:2",
            "total_goals:3",
            "total_goals:4",
            "total_goals:5+",
            "unresolved_tail",
        ]
        .map(str::to_owned),
    );
    v
}
fn validate_stability(id: &str, counts: &[u64]) -> Result<(), SimulationError> {
    for i in 0..counts.len() {
        for j in i + 1..counts.len() {
            let d = counts[i].abs_diff(counts[j]) as f64 / DRAWS_PER_BATCH as f64;
            if d > STABILITY_LIMIT {
                return Err(err(
                    "STABILITY_FAILURE",
                    format!("{id} batch difference {d}"),
                ));
            }
        }
    }
    Ok(())
}
fn clopper_pearson(k: u64, n: u64, alpha: f64) -> Result<IntervalV1, SimulationError> {
    let lower = if k == 0 {
        0.0
    } else {
        Beta::new(k as f64, (n - k + 1) as f64)
            .map_err(|e| err("INTERVAL_FAILURE", e.to_string()))?
            .inverse_cdf(alpha / 2.0)
    };
    let upper = if k == n {
        1.0
    } else {
        Beta::new((k + 1) as f64, (n - k) as f64)
            .map_err(|e| err("INTERVAL_FAILURE", e.to_string()))?
            .inverse_cdf(1.0 - alpha / 2.0)
    };
    if !lower.is_finite() || !upper.is_finite() {
        return Err(err("INTERVAL_FAILURE", "non-finite interval"));
    }
    Ok(IntervalV1 { lower, upper })
}
fn base_seed_commitment(probability_hash: &str) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(PROTOCOL_ID.as_bytes());
    h.update(POLICY_SHA256.as_bytes());
    h.update(probability_hash.as_bytes());
    h.finalize().into()
}
fn batch_seed(base: &[u8; 32], match_id: &str, index: u32) -> [u8; 32] {
    let mut h = Sha256::new();
    h.update(base);
    h.update(match_id.as_bytes());
    h.update(index.to_be_bytes());
    h.finalize().into()
}
fn validate_probability(v: f64) -> Result<(), SimulationError> {
    if !v.is_finite() || !(0.0..=1.0).contains(&v) {
        Err(err(
            "INVALID_PROBABILITY",
            "probability must be finite and in [0,1]",
        ))
    } else {
        Ok(())
    }
}
fn validate_hash(v: &str) -> Result<(), SimulationError> {
    if v.len() != 64
        || !v
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
    {
        Err(err("MALFORMED_INPUT", "invalid SHA-256"))
    } else {
        Ok(())
    }
}
fn canonical_serialize<T: Serialize>(value: &T) -> Result<Vec<u8>, SimulationError> {
    let v = serde_json::to_value(value).map_err(|e| err("SERIALIZATION_FAILURE", e.to_string()))?;
    serde_json::to_vec(&sort_json(v)).map_err(|e| err("SERIALIZATION_FAILURE", e.to_string()))
}
fn sort_json(v: Value) -> Value {
    match v {
        Value::Array(a) => Value::Array(a.into_iter().map(sort_json).collect()),
        Value::Object(o) => Value::Object(
            o.into_iter()
                .map(|(k, v)| (k, sort_json(v)))
                .collect::<BTreeMap<_, _>>()
                .into_iter()
                .collect(),
        ),
        x => x,
    }
}
fn sha256_hex(payload: &[u8]) -> String {
    hex_bytes(&Sha256::digest(payload))
}
fn hex_bytes(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
fn err(code: &'static str, message: impl Into<String>) -> SimulationError {
    SimulationError::new(code, message)
}

#[cfg(test)]
mod tests;
