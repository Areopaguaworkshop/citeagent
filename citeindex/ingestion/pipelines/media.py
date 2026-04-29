import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..models import PipelineResult
from .common import (
    build_merkle_for_nodes,
    build_nodes,
    build_retrieval_index,
    make_basic_csl,
    make_source_id,
)

logger = logging.getLogger(__name__)


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


# ---------------------------------------------------------------------------
# Media source probing
# ---------------------------------------------------------------------------

def _probe_local_media(path: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"source_path": os.path.abspath(path), "title": os.path.basename(path)}
    try:
        from pymediainfo import MediaInfo

        parsed = MediaInfo.parse(path)
        tracks = parsed.tracks
        general = next((t for t in tracks if t.track_type == "General"), None)
        if general:
            metadata["title"] = general.title or metadata["title"]
            metadata["duration_ms"] = general.duration
            metadata["format"] = general.format
            metadata["performer"] = getattr(general, "performer", None)
    except Exception:
        logger.warning("pymediainfo unavailable or failed", exc_info=True)
    return metadata


def _probe_url_media(url: str) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {"url": url, "title": url}
    cmd = ["yt-dlp", "--dump-single-json", "--no-warnings", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode == 0 and proc.stdout.strip():
            info = json.loads(proc.stdout)
            metadata.update(
                {
                    "title": info.get("title") or url,
                    "uploader": info.get("uploader"),
                    "duration_seconds": info.get("duration"),
                    "upload_date": info.get("upload_date"),
                    "platform": info.get("extractor_key") or info.get("extractor"),
                }
            )
    except Exception:
        logger.warning("yt-dlp metadata probe failed", exc_info=True)
    return metadata


# ---------------------------------------------------------------------------
# Media download (URL → file)
# ---------------------------------------------------------------------------

def _download_media(url: str) -> Optional[str]:
    """Download media from URL using yt-dlp. Returns path to downloaded file."""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            cmd = [
                "yt-dlp",
                "-x",  # extract audio
                "--audio-format", "wav",
                "-o", output_template,
                url,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if proc.returncode != 0:
                logger.warning("yt-dlp download failed: %s", proc.stderr[:200])
                return None

            # Find the output file
            for f in os.listdir(tmpdir):
                src = os.path.join(tmpdir, f)
                # Copy to persistent temp location
                dst = os.path.join(tempfile.gettempdir(), f"citeindex_media_{f}")
                import shutil
                shutil.copy2(src, dst)
                return dst
    except Exception:
        logger.warning("Media download failed", exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Audio extraction with ffmpeg
# ---------------------------------------------------------------------------

def _extract_audio(media_path: str) -> Optional[str]:
    """Extract audio track from media file using ffmpeg. Returns path to WAV."""
    try:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"citeindex_audio_{os.path.basename(media_path)}.wav",
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", media_path,
            "-vn",  # no video
            "-acodec", "pcm_s16le",
            "-ar", "16000",  # 16kHz for WhisperX
            "-ac", "1",  # mono
            output_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode == 0 and os.path.exists(output_path):
            logger.info("Audio extracted to %s", output_path)
            return output_path
        logger.warning("ffmpeg audio extraction failed: %s", proc.stderr[:200])
    except Exception:
        logger.warning("ffmpeg not available or failed", exc_info=True)
    return None


# ---------------------------------------------------------------------------
# Transcription with WhisperX
# ---------------------------------------------------------------------------

def _transcribe_whisperx(audio_path: str) -> List[Dict[str, Any]]:
    """Generate timestamped transcript using WhisperX."""
    try:
        import whisperx

        device = "cpu"
        model = whisperx.load_model("base", device=device, compute_type="int8")
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(audio)

        # Word-level alignment
        align_model, align_metadata = whisperx.load_align_model(
            language_code=result.get("language", "en"), device=device
        )
        aligned = whisperx.align(
            result["segments"], align_model, align_metadata, audio, device
        )

        segments: List[Dict[str, Any]] = []
        for seg in aligned.get("segments", result.get("segments", [])):
            segments.append({
                "start": seg.get("start", 0.0),
                "end": seg.get("end", 0.0),
                "text": seg.get("text", ""),
            })

        logger.info("WhisperX transcription produced %d segments", len(segments))
        return segments

    except ImportError:
        logger.info("whisperx not installed, skipping transcription")
        return []
    except Exception:
        logger.warning("WhisperX transcription failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Speaker diarization with pyannote (optional)
# ---------------------------------------------------------------------------

def _diarize_speakers(audio_path: str) -> List[Dict[str, Any]]:
    """Identify speaker segments using pyannote.audio."""
    try:
        from pyannote.audio import Pipeline

        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1")
        diarization = pipeline(audio_path)

        speaker_segments: List[Dict[str, Any]] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            speaker_segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker,
            })

        logger.info("Pyannote diarization found %d speaker turns", len(speaker_segments))
        return speaker_segments

    except ImportError:
        logger.info("pyannote not installed, skipping diarization")
        return []
    except Exception:
        logger.warning("Pyannote diarization failed", exc_info=True)
        return []


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------

def run(media_ref: str) -> PipelineResult:
    source_id = make_source_id(media_ref)
    input_type = "url" if _is_url(media_ref) else "file"

    # Step 1: Probe metadata
    media_metadata = _probe_url_media(media_ref) if input_type == "url" else _probe_local_media(media_ref)

    # Step 2: Resolve media file path
    media_file_path: Optional[str] = None
    downloaded = False

    if input_type == "file":
        media_file_path = os.path.abspath(media_ref)
    else:
        media_file_path = _download_media(media_ref)
        downloaded = True

    # Step 3: Extract audio
    audio_path: Optional[str] = None
    if media_file_path and os.path.exists(media_file_path):
        audio_path = _extract_audio(media_file_path)

    # Step 4: Transcribe
    transcript_segments: List[Dict[str, Any]] = []
    if audio_path and os.path.exists(audio_path):
        transcript_segments = _transcribe_whisperx(audio_path)

    # Step 5: Speaker diarization (optional)
    speaker_segments: List[Dict[str, Any]] = []
    if audio_path and os.path.exists(audio_path) and transcript_segments:
        speaker_segments = _diarize_speakers(audio_path)

    # Fallback: if no transcription, use title as a single segment
    if not transcript_segments and media_metadata.get("title"):
        transcript_segments.append({
            "start": 0.0,
            "end": 0.0,
            "text": media_metadata["title"],
        })

    # Build nodes from transcript
    page_paragraphs = [(1, [seg["text"] for seg in transcript_segments if seg.get("text")])]
    nodes = build_nodes(source_id, page_paragraphs)
    merkle_tree = build_merkle_for_nodes(nodes)
    retrieval_index = build_retrieval_index(nodes)

    # Build CSL JSON
    csl_extra: Dict[str, Any] = {
        "URL": media_ref if input_type == "url" else None,
        "publisher": media_metadata.get("platform"),
        "accessed": {
            "date-parts": [
                [
                    datetime.now(timezone.utc).year,
                    datetime.now(timezone.utc).month,
                    datetime.now(timezone.utc).day,
                ]
            ]
        },
    }
    if media_metadata.get("uploader"):
        csl_extra["author"] = [{"literal": media_metadata["uploader"]}]
    if media_metadata.get("upload_date"):
        date_str = media_metadata["upload_date"]
        if len(date_str) >= 8:
            try:
                csl_extra["issued"] = {
                    "date-parts": [[int(date_str[:4]), int(date_str[4:6]), int(date_str[6:8])]]
                }
            except ValueError:
                pass

    csl_extra = {k: v for k, v in csl_extra.items() if v is not None}
    csl_json = make_basic_csl(
        source_id, media_metadata.get("title") or source_id, "motion_picture", csl_extra
    )

    transcript_json = {
        "source_id": source_id,
        "source_type": "media",
        "metadata": media_metadata,
        "segments": transcript_segments,
        "speaker_segments": speaker_segments,
        "nodes": nodes,
    }

    extra: Dict[str, Any] = {}
    if input_type == "url" and media_file_path and os.path.exists(media_file_path):
        extra["source_snapshot_path"] = media_file_path
        extra["cleanup_source_snapshot"] = True

    # Cleanup temp files
    if audio_path and os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except OSError:
            pass
    if downloaded and media_file_path and os.path.exists(media_file_path) and not extra.get("source_snapshot_path"):
        try:
            os.remove(media_file_path)
        except OSError:
            pass

    return PipelineResult(
        status="ok",
        source_id=source_id,
        resource_type="media",
        csl_json=csl_json,
        transcript_json=transcript_json,
        merkle_tree=merkle_tree,
        media_metadata=media_metadata,
        retrieval_index=retrieval_index,
        extra=extra,
    )
