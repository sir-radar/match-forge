use simulation_core::{parse_canonical_input, run};
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
        .ok_or("usage: pitchapi_v2_validate INPUT SHA256 WORKERS")?;
    let expected_hash = arguments.next().ok_or("missing input SHA-256")?;
    let workers: usize = arguments
        .next()
        .ok_or("missing worker count")?
        .parse()
        .map_err(|_| "worker count must be an integer")?;
    if arguments.next().is_some() {
        return Err("unexpected argument".into());
    }
    let payload = fs::read(path).map_err(|error| format!("cannot read input: {error}"))?;
    let input =
        parse_canonical_input(&payload, &expected_hash).map_err(|error| error.to_string())?;
    let output = run(&input, &expected_hash, workers).map_err(|error| error.to_string())?;
    io::stdout()
        .write_all(
            &output
                .canonical_bytes()
                .map_err(|error| error.to_string())?,
        )
        .map_err(|error| format!("cannot write output: {error}"))?;
    Ok(())
}
