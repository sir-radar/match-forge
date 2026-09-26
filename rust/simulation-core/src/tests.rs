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

fn v3_input() -> SimulationInputV1 {
    SimulationInputV1 {
        policy_sha256: V3_POLICY_SHA256.into(),
        protocol_id: V3_PROTOCOL_ID.into(),
        seed_schedule_id: V3_SEED_SCHEDULE_ID.into(),
        ..input()
    }
}

fn v4_input() -> SimulationInputV1 {
    SimulationInputV1 {
        algorithm_version: V4_ALGORITHM_VERSION.into(),
        policy_sha256: V4_POLICY_SHA256.into(),
        protocol_id: V4_PROTOCOL_ID.into(),
        seed_schedule_id: V4_SEED_SCHEDULE_ID.into(),
        ..input()
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
fn v3_replay_is_stable_and_rejects_v2_identity() {
    let value = v3_input();
    let bytes = canonical_bytes(&value).unwrap();
    let hash = sha256(&bytes);
    assert_eq!(parse_canonical_input_v3(&bytes, &hash).unwrap(), value);
    assert_eq!(
        run_v3(&value, &hash, 1).unwrap(),
        run_v3(&value, &hash, 4).unwrap()
    );
    assert_eq!(
        parse_canonical_input(&bytes, &hash).unwrap_err().code,
        "UNSUPPORTED_IDENTITY"
    );
}

#[test]
fn v4_distribution_gate_replays_across_worker_counts() {
    let value = v4_input();
    let bytes = canonical_bytes(&value).unwrap();
    let hash = sha256(&bytes);
    let one = run_v4(&value, &hash, 1).unwrap();
    let four = run_v4(&value, &hash, 4).unwrap();
    assert_eq!(one, four);
    assert_eq!(one.status, "PASS");
    assert!(one.total_variation <= one.total_variation_limit);
    assert_eq!(parse_canonical_input_v4(&bytes, &hash).unwrap(), value);
}

#[test]
fn v4_recomputes_analytic_indicators_from_atoms() {
    let mut value = v4_input();
    value.analytic_probabilities[0].probability = 0.4;
    let bytes = canonical_bytes(&value).unwrap();
    let hash = sha256(&bytes);
    assert_eq!(
        parse_canonical_input_v4(&bytes, &hash).unwrap_err().code,
        "ANALYTIC_REDUCTION_MISMATCH"
    );
    assert_eq!(
        run_v4(&value, &hash, 1).unwrap_err().code,
        "ANALYTIC_REDUCTION_MISMATCH"
    );
}

#[test]
fn v4_distribution_gate_has_pass_warning_and_fail_paths() {
    let event = |index: usize, error: f64| V4EventValidationV1 {
        absolute_error: error,
        analytic_probability: 0.0,
        batch_counts: vec![0; 4],
        count: 0,
        event_id: format!("event-{index}"),
        simulated_probability: 0.0,
    };
    let pass: Vec<_> = (0..62).map(|index| event(index, 0.0)).collect();
    assert_eq!(validate_v4_distribution(&pass).unwrap(), (0.0, vec![]));

    let warning: Vec<_> = (0..62)
        .map(|index| event(index, if index == 61 { 0.009 } else { 0.0 }))
        .collect();
    let (_, warnings) = validate_v4_distribution(&warning).unwrap();
    assert_eq!(warnings, vec!["event-61 exceeds event warning limit"]);

    let fail: Vec<_> = (0..62)
        .map(|index| event(index, if index < 36 { 0.001 } else { 0.0 }))
        .collect();
    assert_eq!(
        validate_v4_distribution(&fail).unwrap_err().code,
        "DISTRIBUTION_PARITY_FAILURE"
    );
}

#[test]
fn diagnostic_replay_is_stable_across_worker_counts() {
    let value = v3_input();
    let bytes = canonical_bytes(&value).unwrap();
    let hash = sha256(&bytes);
    let one = diagnose_v3(&value, &hash, 1, 6_250).unwrap();
    let four = diagnose_v3(&value, &hash, 4, 6_250).unwrap();
    assert_eq!(one.events, four.events);
    assert_eq!(one.batch_seed_ids, four.batch_seed_ids);
    assert_eq!(one.simulation_count, 25_000);
    assert_eq!(four.simulation_count, 25_000);
}

#[test]
fn asymmetric_score_cells_are_not_reversed() {
    for (home, away) in [(1, 4), (4, 1), (0, 5), (5, 0), (2, 3), (3, 2)] {
        let atoms = vec![
            ScoreAtomV1 {
                away_goals: Some(away),
                home_goals: Some(home),
                kind: AtomKindV1::ExactScore,
                probability: 1.0,
            },
            ScoreAtomV1 {
                away_goals: None,
                home_goals: None,
                kind: AtomKindV1::UnresolvedTail,
                probability: 0.0,
            },
        ];
        let mut value = v3_input();
        value.atoms = atoms;
        value.forecast_probability_sha256 = sha256(&canonical_bytes(&value.atoms).unwrap());
        value.analytic_probabilities = analytic_probabilities(&value.atoms);
        let bytes = canonical_bytes(&value).unwrap();
        let output = diagnose_v3(&value, &sha256(&bytes), 4, 10).unwrap();
        let label = |goals: u16| {
            if goals < 5 {
                goals.to_string()
            } else {
                "5+".into()
            }
        };
        let expected = format!("score:{}-{}", label(home), label(away));
        let reversed = format!("score:{}-{}", label(away), label(home));
        let counts: BTreeMap<_, _> = output
            .events
            .iter()
            .map(|event| (event.event_id.as_str(), event.count))
            .collect();
        assert_eq!(counts[expected.as_str()], 40);
        if expected != reversed {
            assert_eq!(counts[reversed.as_str()], 0);
        }
    }
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
fn canonicalization_is_idempotent_for_small_probabilities() {
    let payload = br#"[{"away_goals":14,"home_goals":1,"kind":"EXACT_SCORE","probability":1.4033441127662814e-13}]"#;
    let once = canonicalize_json(payload).unwrap();
    assert_eq!(canonicalize_json(&once).unwrap(), once);
    let typed = canonicalize_atoms_json(payload).unwrap();
    assert_eq!(canonicalize_atoms_json(&typed).unwrap(), typed);

    let mut value = v3_input();
    value.atoms[0].probability = 1.403_344_112_766_281_4e-13;
    value.atoms[1].probability = 1.0 - value.atoms[0].probability;
    value.forecast_probability_sha256 = sha256(&canonical_bytes(&value.atoms).unwrap());
    value.analytic_probabilities = analytic_probabilities(&value.atoms);
    let bytes = canonical_bytes(&value).unwrap();
    assert_eq!(
        parse_canonical_input_v3(&bytes, &sha256(&bytes)).unwrap(),
        value
    );
}

#[test]
fn invalid_probabilities_counts_atoms_and_worker_fail_closed() {
    let mut value = input();
    value.atoms[0].probability = f64::NAN;
    assert_eq!(
        validate_input_for(&value, PROTOCOL_ID, POLICY_SHA256, SEED_SCHEDULE_ID)
            .unwrap_err()
            .code,
        "INVALID_PROBABILITY"
    );
    value = input();
    value.atoms[0].probability = 1.1;
    assert_eq!(
        validate_input_for(&value, PROTOCOL_ID, POLICY_SHA256, SEED_SCHEDULE_ID)
            .unwrap_err()
            .code,
        "INVALID_PROBABILITY"
    );
    value = input();
    value.simulation_count -= 1;
    assert_eq!(
        validate_input_for(&value, PROTOCOL_ID, POLICY_SHA256, SEED_SCHEDULE_ID)
            .unwrap_err()
            .code,
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
