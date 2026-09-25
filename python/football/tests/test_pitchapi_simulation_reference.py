from football.validation.pitchapi_simulation_reference import (
    SplitMix64,
    base_seed_commitment,
    batch_seed,
    event_indexes,
    selected_atom_indexes,
)


def test_python_reference_golden_vectors() -> None:
    generator = SplitMix64(0)
    assert [generator.next_u64() for _ in range(3)] == [
        0xE220A8397B1DCDAF,
        0x6E789E6AA1B965F4,
        0x06C45D188009454F,
    ]
    base = base_seed_commitment("c" * 64)
    seed = batch_seed(base, "synthetic-match-1", 0)
    assert base.hex() == "c4f0050e1627a07a4e2030beb1b20df55d62549ce4a35e7e2b1ff2d77487560e"
    assert seed.hex() == "a185788a8fcce44299ba16d6e236609aebd759b1cdce490f9ead24fe2fd2fe51"
    assert selected_atom_indexes((0.2, 0.3, 0.5), seed, 8) == (2, 1, 2, 1, 2, 0, 2, 0)
    assert event_indexes(2, 1) == (13, 36, 39, 41, 43, 45, 48, 50, 52, 54, 58)
