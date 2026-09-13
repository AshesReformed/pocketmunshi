"""
PocketMunshi voice pipeline: speech-to-text via Groq's hosted API.

STACK CONSTRAINT: Groq's hosted "whisper-large-v3-turbo" endpoint only.
Do NOT swap in a locally-run Whisper model -- this app targets free
Streamlit Cloud CPU hosting (no GPU) and local Whisper is both slower there
and weaker on Urdu/English code-switched speech than Groq's hosted model.

Requires the `groq` package (in requirements.txt) and a Groq API key from
https://console.groq.com.
"""

from groq import Groq

MODEL = "whisper-large-v3-turbo"


def transcribe_audio(audio_bytes: bytes, api_key: str) -> str:
    """
    Send audio_bytes to Groq's whisper-large-v3-turbo endpoint and return the
    transcript text.

    Raises RuntimeError on any API failure (auth, network, bad audio, etc.)
    rather than silently returning an empty string -- callers need to tell
    "no speech detected" apart from "the API call failed."
    """
    if not audio_bytes:
        raise RuntimeError("transcribe_audio: no audio bytes provided.")

    try:
        client = Groq(api_key=api_key)
        transcription = client.audio.transcriptions.create(
            file=("recording.wav", audio_bytes),
            model=MODEL,
            response_format="text",
            # Pinned to Urdu: on short/quiet clips, Whisper's auto language
            # detection can latch onto the wrong language entirely (observed
            # hallucinating Icelandic on a real test recording). Pinning the
            # primary language sharply reduces that failure mode while still
            # transcribing embedded English words/numbers correctly, which
            # is exactly the Urdu/English code-switched speech this app
            # targets.
            language="ur",
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad, re-raised with context
        raise RuntimeError(f"Groq transcription request failed: {exc}") from exc

    # response_format="text" returns a plain string in the Groq SDK; some
    # SDK versions instead return an object with a `.text` attribute -- handle
    # both so a client library upgrade doesn't silently break this function.
    text = transcription if isinstance(transcription, str) else getattr(
        transcription, "text", None
    )

    if text is None:
        raise RuntimeError(
            "Groq transcription response was in an unexpected shape: "
            f"{transcription!r}"
        )

    return text.strip()
