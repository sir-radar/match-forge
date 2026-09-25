use super::*;

fn atoms() -> Vec<ScoreAtomV1> {
    vec![
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
    ]
}

fn input() -> SimulationInputV1 {
    let atoms = atoms();
    SimulationInputV1 {
        algorithm_version: ALGORITHM_VERSION.into(),
        analytic_probabilities: analytic_probabilities(&atoms),
        forecast_probability_sha256: sha256(&canonical_bytes(&atoms).unwrap()),
        atoms,
        canonical_match_id: "synthetic-match-1".into(),
        forecast_artifact_sha256: "a".repeat(64),
        forecast_id: "synthetic-forecast-1".into(),
        model_artifact_sha256: "b".repeat(64),
        policy_sha256: POLICY_SHA256.into(),
        protocol_id: PROTOCOL_ID.into(),
        schema_version: "PitchApiSimulationInputV1".into(),
        seed_schedule_id: SEED_SCHEDULE_ID.into(),
        simulation_count: SIMULATION_COUNT,
    }
}

#[test]
fn splitmix64_matches_published_vector() {
    let mut rng = SplitMix64::new(0);
    assert_eq!(rng.next_u64(), 0xe220_a839_7b1d_cdaf);
    assert_eq!(rng.next_u64(), 0x6e78_9e6a_a1b9_65f4);
    assert_eq!(rng.next_u64(), 0x06c4_5d18_8009_454f);
}

#[test]
fn seeds_repeat_and_isolate_targets() {
    let base = base_seed_commitment(&"c".repeat(64));
    assert_eq!(
        hex_bytes(&base),
        "c4f0050e1627a07a4e2030beb1b20df55d62549ce4a35e7e2b1ff2d77487560e"
    );
    assert_eq!(
        hex_bytes(&batch_seed(&base, "synthetic-match-1", 0)),
        "a185788a8fcce44299ba16d6e236609aebd759b1cdce490f9ead24fe2fd2fe51"
    );
    assert_eq!(batch_seed(&base, "a", 0), batch_seed(&base, "a", 0));
    assert_ne!(batch_seed(&base, "a", 0), batch_seed(&base, "b", 0));
    assert_ne!(batch_seed(&base, "a", 0), batch_seed(&base, "a", 1));
}

#[test]
fn replay_is_stable_across_worker_counts_and_hashes() {
    let one = run(&input(), &"d".repeat(64), 1).unwrap();
    let four = run(&input(), &"d".repeat(64), 4).unwrap();
    assert_eq!(one, four);
    assert_eq!(
        one.canonical_bytes().unwrap(),
        four.canonical_bytes().unwrap()
    );
    assert_eq!(one.sha256().unwrap(), four.sha256().unwrap());
}

#[test]
fn canonical_round_trip_rejects_hash_and_format_changes() {
    let value = input();
    let bytes = canonical_bytes(&value).unwrap();
    let hash = sha256(&bytes);
    assert_eq!(parse_canonical_input(&bytes, &hash).unwrap(), value);
    assert_eq!(
        parse_canonical_input(&bytes, &"0".repeat(64))
            .unwrap_err()
            .code,
        "INPUT_HASH_MISMATCH"
    );
    let pretty = serde_json::to_vec_pretty(&value).unwrap();
    assert_eq!(
        parse_canonical_input(&pretty, &sha256(&pretty))
            .unwrap_err()
            .code,
        "NON_CANONICAL_INPUT"
    );
    assert_eq!(
        parse_canonical_input(b"{", &sha256(b"{")).unwrap_err().code,
        "MALFORMED_INPUT"
    );
}

#[test]
fn invalid_probabilities_counts_atoms_and_worker_fail_closed() {
    let mut value = input();
    value.atoms[0].probability = f64::NAN;
    assert_eq!(
        validate_input(&value).unwrap_err().code,
        "INVALID_PROBABILITY"
    );
    value = input();
    value.atoms[0].probability = 1.1;
    assert_eq!(
        validate_input(&value).unwrap_err().code,
        "INVALID_PROBABILITY"
    );
    value = input();
    value.simulation_count -= 1;
    assert_eq!(
        validate_input(&value).unwrap_err().code,
        "INVALID_SIMULATION_COUNT"
    );
    assert_eq!(
        run(&input(), &"d".repeat(64), 0).unwrap_err().code,
        "INVALID_WORKER_COUNT"
    );
}

#[test]
fn precision_boundary_proves_exact_count() {
    let pass = clopper_pearson(56_230, 112_460, 0.05 / 62.0).unwrap();
    let fail = clopper_pearson(56_228, 112_456, 0.05 / 62.0).unwrap();
    assert!((pass.upper - pass.lower) / 2.0 <= 0.005);
    assert!((fail.upper - fail.lower) / 2.0 > 0.005);
}

#[test]
fn analytic_reduction_has_all_62_events_and_normalizes_partitions() {
    let values = analytic_probabilities(&atoms());
    assert_eq!(values.len(), 62);
    let map: BTreeMap<_, _> = values
        .into_iter()
        .map(|v| (v.event_id, v.probability))
        .collect();
    assert_eq!(
        map["outcome:home_win"] + map["outcome:draw"] + map["outcome:away_win"],
        1.0
    );
    assert_eq!(map["btts:yes"] + map["btts:no"], 1.0);
}

#[test]
fn synthetic_benchmark_is_parallel_deterministic() {
    assert_eq!(
        benchmark_synthetic_targets(3, 1).unwrap(),
        benchmark_synthetic_targets(3, 4).unwrap()
    );
}
