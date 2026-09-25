use simulation_core::benchmark_synthetic_targets;
use std::env;
use std::time::Instant;

fn main() {
    let targets = env::args()
        .nth(1)
        .and_then(|value| value.parse().ok())
        .unwrap_or(32);
    let workers = env::args()
        .nth(2)
        .and_then(|value| value.parse().ok())
        .unwrap_or(4);
    let started = Instant::now();
    let (draws, checksum) =
        benchmark_synthetic_targets(targets, workers).expect("benchmark failed");
    let seconds = started.elapsed().as_secs_f64();
    println!(
        "{{\"checksum\":{checksum},\"draws\":{draws},\"seconds\":{seconds},\"simulations_per_second\":{},\"synthetic_targets\":{targets},\"workers\":{workers}}}",
        draws as f64 / seconds
    );
}
