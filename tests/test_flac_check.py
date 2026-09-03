"""The FLAC authenticity checker must not cry wolf.

The expensive regression here is not a missed transcode, it is a false
accusation: a genuinely lossless recording that happens to be quiet, old or
sparsely mixed rolls off in the treble, and a naive "how far did the level
drop" test convicts it. That bug was real during development — a lossless
file lowpassed at 11 kHz was reported as an MP3 — so the shape tests below
pin the distinction between a codec wall and an ordinary roll-off.

The pure-logic tests run everywhere. The ones that need ffmpeg build their own
FLACs and skip where the binary is absent, so the CI matrix stays green on
runners that do not ship it.
"""
import hashlib
import os
import shutil
import struct
import subprocess

import pytest

from automation_tools.tools import flac_check


needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg is not installed"
)


# ── Header parsing ───────────────────────────────────────────────────────────
def _streaminfo_bytes(sample_rate=44100, channels=2, bits=16, samples=220500,
                      md5=b"\x11" * 16):
    """A minimal but valid fLaC header, built the way the spec lays it out."""
    packed = (
        (sample_rate << 44) | ((channels - 1) << 41) | ((bits - 1) << 36) | samples
    )
    block = (
        struct.pack(">HH", 4096, 4096)      # min/max block size
        + (1000).to_bytes(3, "big")         # min frame size
        + (2000).to_bytes(3, "big")         # max frame size
        + packed.to_bytes(8, "big")
        + md5
    )
    return b"fLaC" + b"\x00\x00\x00\x22" + block


def test_read_streaminfo_reads_what_the_header_declares(tmp_path):
    path = tmp_path / "song.flac"
    path.write_bytes(_streaminfo_bytes(sample_rate=96000, channels=1, bits=24,
                                       samples=480000))

    info = flac_check.read_streaminfo(str(path))

    assert info is not None
    assert (info.sample_rate, info.channels, info.bits) == (96000, 1, 24)
    assert info.samples == 480000
    assert info.md5 == "11" * 16
    assert info.nyquist == 48000
    assert info.duration == pytest.approx(5.0)


def test_an_all_zero_checksum_means_the_encoder_stored_none(tmp_path):
    """Not every encoder writes one, and an absent checksum is not a mismatch."""
    path = tmp_path / "song.flac"
    path.write_bytes(_streaminfo_bytes(md5=b"\x00" * 16))

    info = flac_check.read_streaminfo(str(path))

    assert info is not None
    assert info.md5 == ""


@pytest.mark.parametrize("payload", [
    b"",
    b"not a flac file at all",
    b"fLaC\x00\x00\x00\x22" + b"\x00" * 10,     # truncated STREAMINFO
])
def test_read_streaminfo_refuses_anything_that_is_not_a_flac(tmp_path, payload):
    path = tmp_path / "thing.flac"
    path.write_bytes(payload)

    assert flac_check.read_streaminfo(str(path)) is None


def test_read_streaminfo_returns_none_for_a_missing_file(tmp_path):
    assert flac_check.read_streaminfo(str(tmp_path / "gone.flac")) is None


# ── Band sweep ───────────────────────────────────────────────────────────────
def test_every_band_in_the_sweep_is_the_same_width():
    """A narrow leftover band measures little because it is narrow, and the
    sweep cannot tell that apart from a codec wall."""
    edges = flac_check.band_edges(22050)

    widths = {edges[i + 1] - edges[i] for i in range(len(edges) - 1)}
    assert widths == {flac_check._BAND_HZ}
    assert edges[-1] <= 22050


def test_the_sweep_stops_short_of_nyquist_on_high_rate_files():
    """No music lives at 40 kHz; the question up there is only whether
    anything survives past CD's ceiling."""
    edges = flac_check.band_edges(48000)

    assert edges[-1] < 48000
    assert edges[-1] > flac_check._CD_BAND_EDGE


def _energies(levels, start=None):
    """Turns a list of per-band dB levels into what band_energies returns."""
    start = flac_check._SWEEP_START_HZ if start is None else start
    step = flac_check._BAND_HZ
    return {
        (start + i * step, start + (i + 1) * step): level
        for i, level in enumerate(levels)
    }


# ── Cutoff detection ─────────────────────────────────────────────────────────
def test_flat_audio_has_no_cutoff():
    assert flac_check.find_cutoff(_energies([-32] * 11)) == (None, False)


def test_a_codec_wall_is_found_where_the_level_falls_off():
    #                        11k              …             19k    20k    21k
    levels = [-32, -32, -32, -32, -32, -32, -32, -32, -32, -50, -80]
    assert flac_check.find_cutoff(_energies(levels)) == (20000, False)


def test_silence_above_the_wall_is_what_confirms_it():
    """Measured from a real library: a wall at 17 kHz over a dead floor.

    The bands above an encoder's cutoff hold nothing and sit flat against each
    other. That floor is the difference between evidence and a guess, so it is
    reported separately from the frequency.
    """
    levels = [-41, -43, -45, -47, -50, -51, -64, -78, -82, -82, -82]

    assert flac_check.find_cutoff(_energies(levels)) == (17000, True)


def test_a_wall_in_the_last_band_cannot_be_confirmed():
    """Around 20 kHz a high-bitrate MP3 and a steep CD master look alike, and
    the sweep has no bands left above to tell them apart."""
    levels = [-36, -37, -40, -42, -43, -45, -43, -44, -43, -48, -90]

    cutoff, floor_observed = flac_check.find_cutoff(_energies(levels))

    assert cutoff == 20000
    assert floor_observed is False


def test_a_wall_needs_more_than_one_big_step_to_be_wide_enough():
    """A drop that never bottoms out in silence is not an encoder."""
    levels = [-32, -32, -32, -32, -32, -32, -32, -32, -32, -40, -45]

    assert flac_check.find_cutoff(_energies(levels)) == (None, False)


def test_a_gradual_roll_off_is_not_a_cutoff():
    """The regression this file exists for.

    These are the measured levels of a genuinely lossless recording lowpassed
    at 11 kHz. The total drop is over 45 dB — more than any transcode — but it
    arrives a few dB at a time, which is what a filter does and what an encoder
    never does.
    """
    levels = [-36, -37, -39, -41, -44, -47, -51, -55, -61, -69, -83]

    assert flac_check.find_cutoff(_energies(levels)) == (None, False)


def test_a_big_step_at_the_end_of_a_ramp_is_still_a_roll_off():
    """A steep filter eventually drops fast, but it does not start flat."""
    levels = [-32, -33, -35, -40, -48, -61, -81]

    assert flac_check.find_cutoff(_energies(levels)) == (None, False)


def test_near_silence_cannot_be_judged_either_way():
    quiet = _energies([-91] * 11)

    assert flac_check.is_measurable(quiet) is False
    assert flac_check.find_cutoff(quiet) == (None, False)


def test_loud_treble_is_measurable():
    assert flac_check.is_measurable(_energies([-32] * 11)) is True


@pytest.mark.parametrize("cutoff,expected", [
    (16000, "MP3 128 kbps or AAC ~96 kbps"),
    (19000, "MP3 192 kbps or AAC 128 kbps"),
    (21000, "MP3 320 kbps or LAME V0"),
])
def test_a_cutoff_is_named_after_the_encoder_that_leaves_it(cutoff, expected):
    assert flac_check.match_profile(cutoff) == expected


def test_a_cutoff_nowhere_near_a_known_encoder_is_left_unnamed():
    assert flac_check.match_profile(12000) is None


# ── Declared format vs. content ──────────────────────────────────────────────
def test_real_high_rate_content_shows_no_deficit():
    energies = _energies([-35] * 15)

    assert flac_check.hires_deficit(energies) == pytest.approx(0.0, abs=0.01)


def test_upsampled_audio_leaves_a_decaying_skirt_above_cd():
    #                                                   22k  23k  24k  25k
    levels = [-32] * 9 + [-33, -35, -40, -48, -61, -81]
    deficit = flac_check.hires_deficit(_energies(levels))

    assert deficit is not None and deficit > flac_check._HIRES_DEFICIT_DB


def test_a_cd_rate_file_has_nothing_above_cd_to_compare():
    assert flac_check.hires_deficit(_energies([-32] * 11)) is None


# ── Verdicts ─────────────────────────────────────────────────────────────────
def _report(**kwargs):
    stream = flac_check.StreamInfo(
        sample_rate=kwargs.pop("sample_rate", 44100),
        channels=2,
        bits=kwargs.pop("bits", 16),
        samples=220500,
        md5=kwargs.pop("md5", "ab" * 16),
    )
    report = flac_check.FlacReport(
        "song.flac", flac_check.INCONCLUSIVE, stream=stream,
        measurable=kwargs.pop("measurable", True), **kwargs,
    )
    flac_check._decide(report)
    return report


def test_full_band_audio_with_a_matching_checksum_is_authentic():
    assert _report(md5_ok=True).status == flac_check.AUTHENTIC


def test_a_cutoff_makes_it_a_transcode():
    report = _report(cutoff_hz=19000, floor_observed=True, md5_ok=True)

    assert report.status == flac_check.TRANSCODED
    assert report.likely_source == "MP3 192 kbps or AAC 128 kbps"


def test_a_checksum_mismatch_outranks_everything_else():
    """It is the one finding here that is proof rather than evidence."""
    report = _report(cutoff_hz=19000, floor_observed=True, md5_ok=False)

    assert report.status == flac_check.CORRUPT


def test_a_high_rate_file_with_nothing_above_cd_is_upscaled():
    report = _report(sample_rate=96000, bits=24, md5_ok=True, hires_deficit_db=25.0)

    assert report.status == flac_check.UPSCALED


def test_a_high_rate_file_that_earns_its_rate_is_authentic():
    report = _report(sample_rate=96000, bits=24, md5_ok=True, hires_deficit_db=0.5)

    assert report.status == flac_check.AUTHENTIC


def test_padding_a_16_bit_recording_out_to_24_is_an_upscale():
    report = _report(bits=24, md5_ok=True, dead_low_bits=8)

    assert report.status == flac_check.UPSCALED


def test_a_track_with_no_treble_is_never_convicted():
    report = _report(measurable=False, md5_ok=True)

    assert report.status == flac_check.INCONCLUSIVE


def test_an_unconfirmed_wall_is_reported_but_not_convicted():
    """The 20 kHz grey zone: say what was measured, do not accuse."""
    report = _report(cutoff_hz=20000, floor_observed=False, md5_ok=True)

    assert report.status == flac_check.INCONCLUSIVE
    assert any("20 kHz" in note for note in report.notes)


def test_inconclusive_does_not_fail_the_run():
    assert flac_check.INCONCLUSIVE not in flac_check.FAILING
    assert flac_check.AUTHENTIC not in flac_check.FAILING


# ── Reporting ────────────────────────────────────────────────────────────────
def test_export_writes_a_row_per_file(tmp_path):
    out = tmp_path / "report.csv"
    reports = [
        _report(cutoff_hz=19000, floor_observed=True, md5_ok=True),
        _report(md5_ok=True),
    ]

    assert flac_check.export_reports(reports, str(out)) is True

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("status,")
    assert flac_check.TRANSCODED in lines[1]


def test_a_missing_path_is_reported_rather_than_raised(tmp_path):
    assert flac_check.run_flac_check(str(tmp_path / "nowhere")) is False


def test_a_folder_with_no_flac_files_is_not_a_failure(tmp_path):
    (tmp_path / "notes.txt").write_text("nothing to see")

    assert flac_check.run_flac_check(str(tmp_path)) is True


def test_scan_only_picks_up_flac_files(tmp_path):
    (tmp_path / "song.flac").write_bytes(_streaminfo_bytes())
    (tmp_path / "song.mp3").write_bytes(b"ID3nope")
    (tmp_path / "cover.jpg").write_bytes(b"\xff\xd8\xff")

    reports = flac_check.scan(str(tmp_path), ffmpeg=None)

    assert [os.path.basename(r.path) for r in reports] == ["song.flac"]


def test_without_ffmpeg_the_header_is_read_but_nothing_is_claimed(tmp_path):
    """Missing ffmpeg must degrade to 'cannot tell', never to a pass."""
    path = tmp_path / "song.flac"
    path.write_bytes(_streaminfo_bytes())

    report = flac_check.analyse(str(path), ffmpeg=None)

    assert report.status == flac_check.INCONCLUSIVE
    assert report.stream is not None and report.stream.sample_rate == 44100
    assert any("ffmpeg" in note for note in report.notes)


# ── End to end, against audio ffmpeg builds for us ───────────────────────────
def _encode(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    """A folder holding one honest FLAC and three kinds of lie."""
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    d = tmp_path_factory.mktemp("library")
    real, mp3 = str(d / "real.flac"), str(d / "step.mp3")

    _encode("-f", "lavfi", "-i", "anoisesrc=d=5:c=white:r=44100:a=0.3",
            "-ac", "2", "-c:a", "flac", "-sample_fmt", "s16", real)
    _encode("-i", real, "-c:a", "libmp3lame", "-b:a", "128k", mp3)
    _encode("-i", mp3, "-c:a", "flac", "-sample_fmt", "s16", str(d / "transcode.flac"))
    _encode("-i", real, "-ar", "96000", "-c:a", "flac", "-sample_fmt", "s32",
            str(d / "upscale.flac"))

    # Corruption: flip a byte in the middle of the audio, leaving the header
    # (and so the stored checksum) intact.
    data = bytearray(open(real, "rb").read())
    data[len(data) // 2] ^= 0xFF
    (d / "corrupt.flac").write_bytes(bytes(data))

    os.remove(mp3)
    return d


@needs_ffmpeg
@pytest.mark.parametrize("name,expected", [
    ("real.flac", flac_check.AUTHENTIC),
    ("transcode.flac", flac_check.TRANSCODED),
    ("upscale.flac", flac_check.UPSCALED),
    ("corrupt.flac", flac_check.CORRUPT),
])
def test_each_kind_of_file_gets_the_right_verdict(library, name, expected):
    report = flac_check.analyse(str(library / name),
                                ffmpeg=flac_check.ffmpeg_binary(), seconds=5)

    assert report.status == expected


@needs_ffmpeg
def test_the_stored_checksum_matches_what_the_file_decodes_to(library):
    path = str(library / "real.flac")
    stream = flac_check.read_streaminfo(path)
    assert stream is not None and stream.md5

    matches, _dead = flac_check.verify_md5(path, stream, flac_check.ffmpeg_binary())

    assert matches is True
    # And it really is the MD5 of the decoded samples, not of the file.
    decoded = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-"],
        check=True, capture_output=True,
    ).stdout
    assert hashlib.md5(decoded).hexdigest() == stream.md5


@needs_ffmpeg
def test_a_scan_fails_the_run_and_still_reports_the_honest_file(library, capsys):
    ok = flac_check.run_flac_check(str(library), show_all=True)
    out = capsys.readouterr().out

    assert ok is False
    assert "transcode.flac" in out
    assert "real.flac" in out


@needs_ffmpeg
def test_spectrograms_land_in_the_folder_that_was_asked_for(library, tmp_path):
    out_dir = tmp_path / "spectra"

    flac_check.run_flac_check(str(library), spectrogram_dir=str(out_dir),
                              check_md5=False, seconds=5)

    assert (out_dir / "real.png").exists()
