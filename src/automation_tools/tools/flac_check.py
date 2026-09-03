import argparse
import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from rich.table import Table

from automation_tools.core import fs
from automation_tools.core.report import export_rows
from automation_tools.core.logger import (
    console,
    print_error,
    print_step,
    print_success,
    print_warning,
)

# Checks whether the audio inside a .flac is really lossless.
#
# `file_type` proves a file is a FLAC and `integrity` proves it has not
# changed. Neither can tell you the most common lie in a music library: an MP3
# that somebody decoded and re-encoded to FLAC. The container is honest, the
# bytes really are FLAC, but the audio lost everything the MP3 threw away
# years ago. It is bigger than the MP3 and sounds exactly the same.
#
# Three independent checks, cheapest first:
#
#   1. Spectral cutoff. A lossy encoder discards everything above a fixed
#      frequency. Real audio keeps going up to Nyquist; a transcode falls off
#      a cliff. Measured by pushing the signal through brick-wall bands and
#      reading each band's level, all in one decoding pass.
#   2. STREAMINFO checksum. FLAC stores an MD5 of its own decoded audio in the
#      header. Recomputing it catches corruption and tampering outright — this
#      is the one verdict here that is proof rather than evidence.
#   3. Declared format vs. content. A "24-bit / 96 kHz" master that holds
#      nothing above 22.05 kHz is a 16/44.1 file wearing a costume.
#
# ffmpeg does the decoding and the filtering, so there is no numpy, no scipy
# and no C extension to build: the same constraint the rest of the toolkit
# follows. Without ffmpeg the header checks still run and the rest is
# reported as skipped, never as a pass.
#
# What a verdict means:
#   authentic     full-band audio, and the stored checksum matches.
#   transcoded    a sharp cutoff where a lossy encoder puts one. Was an MP3.
#   upscaled      sample rate or bit depth is larger than the audio in it.
#   corrupt       the file's own MD5 does not match what it decodes to.
#   inconclusive  not enough treble to judge. Quiet, old and sparse
#                 recordings land here, and that is the point: no accusation
#                 without evidence.
#   unreadable    not a FLAC, or ffmpeg could not decode it.

DEFAULT_EXCLUDES = list(fs.DEFAULT_EXCLUDES)

_FLAC_MAGIC = b"fLaC"
_STREAMINFO_BYTES = 34

# Where the sweep starts. Low enough to catch the wall a 64 kbps encoder
# leaves, high enough that the first band is still loud in ordinary music and
# can serve as the reference.
_SWEEP_START_HZ = 11000
_BAND_HZ = 1000

# A band quieter than this holds nothing worth measuring.
_FLOOR_DB = -70.0

# What separates a codec wall from a recording that is simply dull.
#
# A lossy encoder truncates: the spectrum is flat and then it is gone, a drop
# of 15 to 50 dB between two neighbouring 1 kHz bands. A quiet or old
# recording rolls off instead, a few dB per band, accelerating smoothly — and
# measured over the whole sweep that roll-off also adds up to tens of dB,
# which is why a total-drop test calls genuine lossless files fake. So the
# wall has to be a concentrated drop coming off a flat stretch — and measured
# across a short window, because at 1 kHz resolution a real encoder's wall
# lands between two bands and reads as two large steps rather than one.
_WALL_DB = 20.0        # cumulative drop across the window that counts as a wall
_WALL_SPAN = 2         # bands the drop may be spread over
_SLOPE_DB = 4.0        # one-step drop that is just a roll-off
_PLATEAU_BANDS = 3     # flat bands required in front of a wall

# What lies above a wall is nothing at all: an encoder writes zeroes, so the
# remaining bands sit flat against each other and far under the music. A
# roll-off keeps declining instead, and never flattens out.
_TAIL_FLAT_DB = 4.0    # spread allowed among the bands above a wall
_TAIL_DEPTH_DB = 25.0  # how far under the reference that floor must sit
# When the wall lands at the top of the sweep there is no floor left to look
# at, so the drop has to bottom out in outright silence to count.
_SILENCE_DB = -75.0

# Seconds of audio to analyse, taken from the middle of the track: intros are
# often quiet, and a quiet passage has no treble to measure either way.
_ANALYSIS_SECONDS = 30

# FLAC's stored MD5 covers the raw samples at exactly the declared depth.
_PCM_FORMATS = {8: "u8", 16: "s16le", 24: "s24le", 32: "s32le"}

# Cutoff (Hz) → the encoder that leaves one there. The bands are 1 kHz wide,
# so neighbouring bitrates cannot be told apart and the labels say so rather
# than naming a number the measurement does not support.
_LOSSY_PROFILES: Tuple[Tuple[int, str], ...] = (
    (13000, "MP3 64 kbps or a heavily compressed stream"),
    (15000, "MP3 96-112 kbps or AAC ~64 kbps"),
    (16000, "MP3 128 kbps or AAC ~96 kbps"),
    (17000, "MP3 128-160 kbps"),
    (18000, "MP3 ~160 kbps or AAC ~112 kbps"),
    (19000, "MP3 192 kbps or AAC 128 kbps"),
    (20000, "MP3 256-320 kbps or LAME V2"),
    (21000, "MP3 320 kbps or LAME V0"),
)
_PROFILE_TOL_HZ = 600

# CD audio's ceiling, and the band boundary that stands in for it. Anything
# claiming a higher rate has to justify it with content above this line.
_CD_NYQUIST_HZ = 22050
_CD_BAND_EDGE = 22000
# How far the above-CD bands may sit below the rest before the extra sample
# rate is decoration. A resampler leaves a shallow skirt there; genuine 96 kHz
# content is as loud up there as it is below.
_HIRES_DEFICIT_DB = 10.0

# Long enough for a full decode of a long track on slow hardware, short enough
# that a wedged process does not hang a library scan forever.
_FFMPEG_TIMEOUT = 900

AUTHENTIC = "authentic"
TRANSCODED = "transcoded"
UPSCALED = "upscaled"
CORRUPT = "corrupt"
INCONCLUSIVE = "inconclusive"
UNREADABLE = "unreadable"

# The verdicts that make a run fail.
FAILING = (TRANSCODED, UPSCALED, CORRUPT, UNREADABLE)

_VOLUME_RE = re.compile(
    r"Parsed_volumedetect_(\d+) @[^\]]*\]\s*mean_volume:\s*(-?[\d.]+) dB"
)


@dataclass
class StreamInfo:
    """What a FLAC says about itself in its own header."""
    sample_rate: int
    channels: int
    bits: int
    samples: int
    md5: str = ""          # "" when the encoder stored no checksum

    @property
    def nyquist(self) -> int:
        return self.sample_rate // 2

    @property
    def duration(self) -> float:
        if not self.sample_rate:
            return 0.0
        return self.samples / float(self.sample_rate)


@dataclass
class FlacReport:
    """Everything one file's analysis found."""
    path: str
    status: str
    stream: Optional[StreamInfo] = None
    cutoff_hz: Optional[int] = None
    likely_source: Optional[str] = None
    md5_ok: Optional[bool] = None      # None: not stored, or not checked
    dead_low_bits: int = 0
    measurable: bool = False           # was there any treble to judge?
    floor_observed: bool = False       # was there silence above the wall to see?
    hires_deficit_db: Optional[float] = None
    notes: List[str] = field(default_factory=list)

    @property
    def format_label(self) -> str:
        if not self.stream:
            return "?"
        s = self.stream
        return f"{s.bits}-bit / {s.sample_rate / 1000:g} kHz"

    @property
    def cutoff_label(self) -> str:
        if self.cutoff_hz is None:
            return "—"
        return f"{self.cutoff_hz / 1000:g} kHz"


# ── Header ───────────────────────────────────────────────────────────────────
def read_streaminfo(path: str) -> Optional[StreamInfo]:
    """Parses the STREAMINFO block, or None if this is not a readable FLAC.

    STREAMINFO is always the first metadata block, and its interesting half is
    a single 64-bit field: sample rate (20 bits), channels - 1 (3), bits per
    sample - 1 (5), then the total sample count (36). The 16 bytes after it are
    an MD5 of the decoded audio, left all-zero by encoders that skip it.
    """
    try:
        with open(path, "rb") as handle:
            if handle.read(4) != _FLAC_MAGIC:
                return None
            handle.read(4)                      # block header: type and length
            block = handle.read(_STREAMINFO_BYTES)
    except OSError:
        return None
    if len(block) < _STREAMINFO_BYTES:
        return None

    packed = int.from_bytes(block[10:18], "big")
    sample_rate = (packed >> 44) & 0xFFFFF
    channels = ((packed >> 41) & 0x7) + 1
    bits = ((packed >> 36) & 0x1F) + 1
    samples = packed & 0xFFFFFFFFF
    digest = block[18:34]
    if not sample_rate:
        return None
    return StreamInfo(
        sample_rate=sample_rate,
        channels=channels,
        bits=bits,
        samples=samples,
        md5="" if digest == b"\x00" * 16 else digest.hex(),
    )


# ── ffmpeg ───────────────────────────────────────────────────────────────────
def ffmpeg_binary() -> Optional[str]:
    """Path to ffmpeg if one is installed, else None."""
    return shutil.which("ffmpeg")


def band_edges(nyquist: int) -> List[int]:
    """The band boundaries to sweep for a given Nyquist frequency.

    Every band is exactly _BAND_HZ wide. A narrower leftover band at the top
    would measure almost nothing simply because it is narrow, and a sweep
    cannot tell that apart from a codec wall, so the sweep stops at the last
    whole band instead.
    """
    ceiling = min(nyquist, _CD_NYQUIST_HZ + 4 * _BAND_HZ)
    edges = list(range(_SWEEP_START_HZ, ceiling + 1, _BAND_HZ))
    return edges if len(edges) >= 2 else []


def band_energies(path: str, edges: Sequence[int], ffmpeg: str,
                  seconds: int = _ANALYSIS_SECONDS,
                  start: float = 0.0) -> Dict[Tuple[int, int], float]:
    """Mean level, in dBFS, of each band between consecutive `edges`.

    One decode feeds every band at once: `asplit` fans the stream out, each
    branch keeps a single band with a brick-wall filter, and volumedetect
    reports what survived. Running one ffmpeg per band instead would decode the
    same track eight times.
    """
    count = len(edges) - 1
    if count < 1:
        return {}

    labels = [f"a{i}" for i in range(count)]
    chains = ["asplit=%d%s" % (count, "".join(f"[{label}]" for label in labels))]
    for index, label in enumerate(labels):
        low, high = edges[index], edges[index + 1]
        chains.append(
            f"[{label}]firequalizer=gain='if(between(f,{low},{high}),0,-200)'"
            f":fft2=on,volumedetect[o{index}]"
        )

    command = [ffmpeg, "-hide_banner", "-nostats"]
    if start > 0:
        command += ["-ss", f"{start:.3f}"]
    command += ["-t", str(seconds), "-i", path, "-filter_complex", ";".join(chains)]
    for index in range(count):
        command += ["-map", f"[o{index}]", "-f", "null", "-"]

    try:
        finished = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=_FFMPEG_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return {}

    stderr = finished.stderr.decode("utf-8", "replace")
    # ffmpeg numbers every filter in the graph, so the volumedetect instances
    # are 2, 4, 6 … with the firequalizers in between. Their order is the band
    # order; their numbers are not, so sort and zip rather than index.
    measured = {int(m.group(1)): float(m.group(2)) for m in _VOLUME_RE.finditer(stderr)}
    if len(measured) != count:
        return {}
    levels = [measured[key] for key in sorted(measured)]
    return {
        (edges[i], edges[i + 1]): levels[i] for i in range(count)
    }


def verify_md5(path: str, stream: StreamInfo, ffmpeg: str) -> Tuple[Optional[bool], int]:
    """Recomputes the stored checksum, and counts always-zero low bits.

    Both answers come out of the same decode because the expensive part is the
    decode, not the arithmetic. The low-bit count is what exposes a 16-bit
    recording padded out to 24: those bytes never change.

    Returns (matches, dead_low_bits); matches is None when it could not run.
    """
    pcm_format = _PCM_FORMATS.get(stream.bits)
    if pcm_format is None:
        return None, 0

    command = [ffmpeg, "-v", "error", "-i", path, "-f", pcm_format, "-"]
    stride = max(stream.bits // 8, 1)
    digest = hashlib.md5()
    low_bits = 0
    tail = b""

    try:
        with subprocess.Popen(command, stdout=subprocess.PIPE,
                              stderr=subprocess.DEVNULL) as process:
            assert process.stdout is not None
            while True:
                chunk = process.stdout.read(65536)
                if not chunk:
                    break
                digest.update(chunk)
                if stride > 1:
                    # Sample boundaries do not respect read boundaries, so
                    # carry the partial sample over into the next chunk.
                    buffered = tail + chunk
                    usable = len(buffered) - (len(buffered) % stride)
                    for byte in buffered[:usable:stride]:
                        low_bits |= byte
                    tail = buffered[usable:]
            if process.wait(timeout=_FFMPEG_TIMEOUT) != 0:
                return None, 0
    except (subprocess.SubprocessError, OSError):
        return None, 0

    dead = 0
    if stride > 1:
        while dead < 8 and not (low_bits >> dead) & 1:
            dead += 1
        if low_bits == 0:
            dead = 8
    if not stream.md5:
        return None, dead
    return digest.hexdigest() == stream.md5, dead


def write_spectrogram(path: str, out_png: str, ffmpeg: str) -> bool:
    """Renders the spectrum to a PNG so a borderline verdict can be eyeballed."""
    command = [
        ffmpeg, "-v", "error", "-y", "-i", path,
        "-lavfi", "showspectrumpic=s=1024x512:mode=combined:legend=1:scale=log",
        out_png,
    ]
    try:
        finished = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=_FFMPEG_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return finished.returncode == 0


# ── Analysis ─────────────────────────────────────────────────────────────────
def is_measurable(energies: Dict[Tuple[int, int], float]) -> bool:
    """Whether there is enough signal in the sweep to conclude anything.

    If even the lowest band is near silence the track has no treble to begin
    with — a solo piano, a 1950s master, a fade. There is nothing to measure,
    which is not the same as finding nothing wrong.
    """
    if not energies:
        return False
    return energies[sorted(energies)[0]] >= _FLOOR_DB


def find_cutoff(energies: Dict[Tuple[int, int], float]) -> Tuple[Optional[int], bool]:
    """Where a lossy encoder truncated the audio, and how sure we can be.

    Looks for a large drop that comes off a flat stretch. Both halves matter:
    size alone convicts any recording with a steep roll-off, since a smooth
    slope eventually adds up to the same total drop.

    Returns (frequency, floor_observed). The flag is the difference between
    evidence and a guess. A wall in the middle of the sweep leaves bands above
    it to inspect, and an encoder's silence up there is unmistakable. A wall in
    the last band leaves nothing to inspect, and around 20 kHz a high-bitrate
    MP3 and a steeply filtered CD master look exactly alike.
    """
    if not is_measurable(energies):
        return None, False
    bands = sorted(energies)
    levels = [energies[band] for band in bands]
    reference = levels[0]

    for index in range(1, len(levels)):
        window = levels[index:index + _WALL_SPAN]
        bottom = min(window)
        if levels[index - 1] - bottom < _WALL_DB:
            continue

        # Look back over the run-up. A wall stands at the end of a plateau; a
        # roll-off has already been falling for a while by the time it drops
        # this far, so its first big step is the end of a curve, not a wall.
        start = max(1, index - _PLATEAU_BANDS)
        run_up = [levels[j - 1] - levels[j] for j in range(start, index)]
        if not all(previous < _SLOPE_DB for previous in run_up):
            return None, False

        # And look at what is left above it. An encoder writes silence up
        # there, flat and deep; a recording that is merely dark keeps sloping.
        tail = levels[index + window.index(bottom) + 1:]
        if len(tail) >= 2:
            if max(tail) - min(tail) > _TAIL_FLAT_DB:
                return None, False
            if sum(tail) / len(tail) > reference - _TAIL_DEPTH_DB:
                return None, False
            return bands[index][0], True
        if bottom > _SILENCE_DB:
            return None, False
        return bands[index][0], False
    return None, False


def hires_deficit(energies: Dict[Tuple[int, int], float]) -> Optional[float]:
    """How far the content above CD's ceiling sits below the rest, in dB.

    The question a "96 kHz" file has to answer. Upsampling leaves a decaying
    skirt up there instead of audio, and a skirt measures tens of dB down.
    """
    below = [level for band, level in energies.items() if band[1] <= _CD_BAND_EDGE]
    above = [level for band, level in energies.items() if band[0] >= _CD_BAND_EDGE]
    if not below or not above:
        return None
    return sum(below) / len(below) - sum(above) / len(above)


def match_profile(cutoff_hz: int) -> Optional[str]:
    """The encoder a given cutoff points at, if any is a close enough fit."""
    for frequency, name in _LOSSY_PROFILES:
        if abs(cutoff_hz - frequency) <= _PROFILE_TOL_HZ:
            return name
    return None


def analyse(path: str, ffmpeg: Optional[str] = None, check_md5: bool = True,
            seconds: int = _ANALYSIS_SECONDS,
            spectrogram_dir: Optional[str] = None) -> FlacReport:
    """Runs every available check on one file and reaches a verdict."""
    stream = read_streaminfo(path)
    if stream is None:
        return FlacReport(path, UNREADABLE, notes=["Not a readable FLAC file."])

    report = FlacReport(path, INCONCLUSIVE, stream=stream)
    if ffmpeg is None:
        report.notes.append("ffmpeg not found: only the header could be read.")
        return report

    # Analyse the middle of the track. The opening seconds are often a fade-in
    # with no high frequencies in them at all.
    start = 0.0
    if stream.duration > seconds:
        start = (stream.duration - seconds) / 2

    edges = band_edges(stream.nyquist)
    energies = band_energies(path, edges, ffmpeg, seconds=seconds, start=start)
    if not energies:
        report.status = UNREADABLE
        report.notes.append("ffmpeg could not analyse the audio.")
        return report

    report.measurable = is_measurable(energies)
    report.cutoff_hz, report.floor_observed = find_cutoff(energies)
    report.hires_deficit_db = hires_deficit(energies)

    if check_md5:
        report.md5_ok, report.dead_low_bits = verify_md5(path, stream, ffmpeg)
        if not stream.md5:
            report.notes.append("No checksum stored in this file to verify.")

    if spectrogram_dir:
        stem = os.path.splitext(os.path.basename(path))[0]
        out_png = os.path.join(spectrogram_dir, f"{stem}.png")
        if write_spectrogram(path, out_png, ffmpeg):
            report.notes.append(f"Spectrogram: {out_png}")
        else:
            report.notes.append("Spectrogram could not be rendered.")

    _decide(report)
    return report


def _decide(report: FlacReport) -> None:
    """Turns the measurements into a verdict, worst finding first."""
    stream = report.stream
    if stream is None:
        report.status = UNREADABLE
        return

    if report.md5_ok is False:
        report.status = CORRUPT
        report.notes.append(
            "The audio does not match the checksum the file carries."
        )
        return

    if not report.measurable:
        report.status = INCONCLUSIVE
        report.notes.append(
            "Too little high-frequency content to judge. Normal for quiet, "
            "sparse or old recordings, and for silence."
        )
        return

    cutoff = report.cutoff_hz
    if cutoff is not None and report.floor_observed:
        report.status = TRANSCODED
        report.likely_source = match_profile(cutoff)
        where = (f"where {report.likely_source} stops"
                 if report.likely_source else "where no lossless source would")
        report.notes.append(
            f"Audio stops dead at {cutoff / 1000:g} kHz, {where}, and there is "
            "nothing but silence above it."
        )
        return
    if cutoff is not None:
        # The wall is in the last band the sweep can see, so there is no
        # silence above it to confirm. Say what was measured and stop there.
        report.status = INCONCLUSIVE
        report.likely_source = match_profile(cutoff)
        report.notes.append(
            f"Content stops abruptly at {cutoff / 1000:g} kHz. That is where "
            f"{report.likely_source or 'a high-bitrate encoder'} cuts, but also "
            "where a steeply filtered CD master ends, and the sweep cannot see "
            "past it. Check the spectrogram."
        )
        return

    # A rate above CD has to be paid for in content above CD's ceiling.
    deficit = report.hires_deficit_db
    if (stream.sample_rate > 48000 and deficit is not None
            and deficit > _HIRES_DEFICIT_DB):
        report.status = UPSCALED
        report.notes.append(
            f"Declared {stream.sample_rate / 1000:g} kHz, but above 22 kHz the "
            f"signal is {deficit:.0f} dB down: resampled from a 44.1 or 48 kHz "
            "source."
        )
        return
    if stream.bits > 16 and report.dead_low_bits >= 8:
        report.status = UPSCALED
        report.notes.append(
            f"Declared {stream.bits}-bit but the low 8 bits are always zero: "
            "padded from 16-bit."
        )
        return

    report.status = AUTHENTIC


# ── Scanning ─────────────────────────────────────────────────────────────────
def scan(path: str, recursive: bool = True, excludes: Optional[List[str]] = None,
         ffmpeg: Optional[str] = None, check_md5: bool = True,
         seconds: int = _ANALYSIS_SECONDS,
         spectrogram_dir: Optional[str] = None) -> List[FlacReport]:
    """Analyses one file, or every .flac under a folder."""
    patterns = list(DEFAULT_EXCLUDES) + list(excludes or [])
    return [
        analyse(full, ffmpeg=ffmpeg, check_md5=check_md5, seconds=seconds,
                spectrogram_dir=spectrogram_dir)
        for full in fs.walk_files(path, recursive=recursive, excludes=patterns,
                                  extensions=(".flac",))
    ]


# ── Reporting ────────────────────────────────────────────────────────────────
_STATUS_STYLE = {
    AUTHENTIC:    ("[green]✓ Authentic[/green]", "green"),
    TRANSCODED:   ("[red]✗ Transcoded from lossy[/red]", "red"),
    UPSCALED:     ("[red]✗ Upscaled format[/red]", "red"),
    CORRUPT:      ("[red]✗ Checksum mismatch[/red]", "red"),
    INCONCLUSIVE: ("[yellow]? Inconclusive[/yellow]", "yellow"),
    UNREADABLE:   ("[dim]· Unreadable[/dim]", "dim"),
}


def _print_summary(reports: List[FlacReport]) -> Dict[str, int]:
    counts = {status: 0 for status in _STATUS_STYLE}
    for report in reports:
        counts[report.status] += 1

    table = Table(title="FLAC authenticity report", header_style="bold cyan")
    table.add_column("Result")
    table.add_column("Files", justify="right")
    for status, (label, _) in _STATUS_STYLE.items():
        table.add_row(label, str(counts[status]))
    console.print(table)
    return counts


def _display_path(path: str, root: str) -> str:
    """The path as the user thinks of it: relative to the folder they scanned.

    A music library is nested three deep and lives under a long absolute path.
    "Artist/Album/03 Track.flac" identifies the file; the same name preceded by
    sixty characters of prefix wraps over three lines and identifies nothing.
    """
    if os.path.isdir(root):
        try:
            return os.path.relpath(path, root)
        except ValueError:           # different drive on Windows
            return path
    return os.path.basename(path)


def _print_details(reports: List[FlacReport], statuses: Sequence[str],
                   title: str, title_style: str, root: str = "",
                   limit: int = 40) -> None:
    rows = [r for r in reports if r.status in statuses]
    if not rows:
        return
    table = Table(title=title, header_style="bold cyan",
                  title_style=title_style, expand=True)
    # The path comes first and takes whatever is left: in an 80-column terminal
    # a row of fixed-width columns squeezes it to nothing, and a verdict you
    # cannot attach to a file is useless. What the cutoff implies is already
    # spelled out in the notes underneath, so it gets no column of its own.
    table.add_column("File", overflow="fold", ratio=1)
    table.add_column("Verdict", width=12)
    table.add_column("Format", width=16)
    table.add_column("Cuts at", width=8, justify="right")
    for report in rows[:limit]:
        table.add_row(
            _display_path(report.path, root),
            report.status,
            report.format_label,
            report.cutoff_label,
        )
    console.print(table)
    if len(rows) > limit:
        console.print(f"[dim]... and {len(rows) - limit} more (hidden).[/dim]")


def export_reports(reports: List[FlacReport], out_path: str) -> bool:
    """Writes every report to `out_path` as CSV."""
    return export_rows(
        out_path,
        ["status", "sample_rate", "bits", "channels", "cutoff_hz",
         "likely_source", "md5", "path", "notes"],
        (
            [
                r.status,
                r.stream.sample_rate if r.stream else "",
                r.stream.bits if r.stream else "",
                r.stream.channels if r.stream else "",
                r.cutoff_hz if r.cutoff_hz is not None else "",
                r.likely_source or "",
                "" if r.md5_ok is None else ("ok" if r.md5_ok else "mismatch"),
                r.path,
                " ".join(r.notes),
            ]
            for r in reports
        ),
    )


# ── Entry point ──────────────────────────────────────────────────────────────
def run_flac_check(
    path: str,
    recursive: bool = True,
    excludes: Optional[List[str]] = None,
    export_path: Optional[str] = None,
    spectrogram_dir: Optional[str] = None,
    check_md5: bool = True,
    seconds: int = _ANALYSIS_SECONDS,
    show_all: bool = False,
) -> bool:
    """Verifies that FLAC files really hold lossless audio.

    Returns False when at least one file is a transcode, an upscale, corrupt
    or unreadable, so the exit code carries the verdict. Inconclusive files
    are not a failure: a recording with no treble simply cannot be judged this
    way, and guessing would be worse than saying so.
    """
    if not os.path.exists(path):
        print_error(f"The path '{path}' does not exist.")
        return False

    ffmpeg = ffmpeg_binary()
    if ffmpeg is None:
        print_warning(
            "ffmpeg was not found, so only the file headers can be read. "
            "Install it to analyse the audio itself."
        )

    if spectrogram_dir:
        try:
            os.makedirs(spectrogram_dir, exist_ok=True)
        except OSError as e:
            print_error(f"Could not create '{spectrogram_dir}': {e}")
            return False

    print_step(f"Analysing FLAC files in [bold]{path}[/bold]…")
    if ffmpeg and check_md5:
        console.print(
            "[dim]Checksum verification decodes every file in full; "
            "use --no-md5 for a faster spectral-only pass.[/dim]"
        )
    elif ffmpeg:
        console.print(
            "[dim]Checksums not verified (--no-md5): the spectrum is measured, "
            "corruption is not.[/dim]"
        )

    reports = scan(
        path, recursive=recursive, excludes=excludes, ffmpeg=ffmpeg,
        check_md5=check_md5, seconds=seconds, spectrogram_dir=spectrogram_dir,
    )
    if not reports:
        print_warning("No .flac files to check.")
        return True

    counts = _print_summary(reports)

    _print_details(
        reports, (TRANSCODED, UPSCALED, CORRUPT),
        "Not what they claim to be", "bold red", root=path,
    )
    _print_details(
        reports, (INCONCLUSIVE, UNREADABLE),
        "Could not be judged", "bold yellow", root=path, limit=20,
    )
    if show_all:
        _print_details(reports, (AUTHENTIC,), "Verified lossless", "bold green",
                       root=path)

    for report in reports:
        if report.status in FAILING or show_all:
            for note in report.notes:
                console.print(f"  [dim]{_display_path(report.path, path)}: {note}[/dim]")

    if export_path:
        export_reports(reports, export_path)

    failures = sum(counts[status] for status in FAILING)
    if failures:
        print_error(
            f"{failures} file(s) are not genuine lossless copies. A cutoff is "
            "strong evidence, not a confession: check the spectrogram before "
            "deleting anything."
        )
        return False

    print_success(f"{counts[AUTHENTIC]} file(s) verified as genuine lossless audio.")
    if counts[INCONCLUSIVE]:
        console.print(
            f"[dim]{counts[INCONCLUSIVE]} file(s) had too little high-frequency "
            "content to judge (quiet, sparse or old recordings).[/dim]"
        )
    return True


def main() -> None:
    """CLI entry point for the FLAC Authenticity Checker."""
    parser = argparse.ArgumentParser(
        description="Check whether .flac files really hold lossless audio."
    )
    parser.add_argument("path", help="FLAC file or folder to check.")
    parser.add_argument("--no-recursive", action="store_true",
                        help="Do not recurse into subfolders.")
    parser.add_argument("-x", "--exclude", nargs="*", default=[],
                        help="Glob patterns to skip (e.g. 'demos/*').")
    parser.add_argument("--export", help="Write a CSV report to this path.")
    parser.add_argument("--spectrograms", metavar="DIR",
                        help="Render a spectrum PNG per file into this folder.")
    parser.add_argument("--no-md5", action="store_true",
                        help="Skip checksum verification (much faster).")
    parser.add_argument("--seconds", type=int, default=_ANALYSIS_SECONDS,
                        help="Seconds of audio to analyse per file.")
    parser.add_argument("--all", action="store_true",
                        help="Also list the files that passed.")
    args = parser.parse_args()

    ok = run_flac_check(
        path=args.path,
        recursive=not args.no_recursive,
        excludes=args.exclude,
        export_path=args.export,
        spectrogram_dir=args.spectrograms,
        check_md5=not args.no_md5,
        seconds=args.seconds,
        show_all=args.all,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
