use simulation_core::{diagnose_v3, parse_canonical_input_v3};
use std::env;
use std::fs;
use std::io::{self, Write};
use std::process::ExitCode;

fn main() -> ExitCode {
    match execute() {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

fn execute() -> Result<(), String> {
    let mut arguments = env::args().skip(1);
    let path = arguments
        .next()
        .ok_or("usage: pitchapi_parity_investigate INPUT SHA256 WORKERS DRAWS_PER_BATCH")?;
    let expected_hash = arguments.next().ok_or("missing input SHA-256")?;
    let workers: usize = arguments
        .next()
        .ok_or("missing worker count")?
        .parse()
        .map_err(|_| "worker count must be an integer")?;
    let draws_per_batch: u64 = arguments
        .next()
        .ok_or("missing draws per batch")?
        .parse()
        .map_err(|_| "draws per batch must be an integer")?;
    if arguments.next().is_some() {
        return Err("unexpected argument".into());
    }
    let payload = fs::read(path).map_err(|error| format!("cannot read input: {error}"))?;
    let input =
        parse_canonical_input_v3(&payload, &expected_hash).map_err(|error| error.to_string())?;
    let output = diagnose_v3(&input, &expected_hash, workers, draws_per_batch)
        .map_err(|error| error.to_string())?;
    io::stdout()
        .write_all(
            &output
                .canonical_bytes()
                .map_err(|error| error.to_string())?,
        )
        .map_err(|error| format!("cannot write output: {error}"))?;
    Ok(())
}
