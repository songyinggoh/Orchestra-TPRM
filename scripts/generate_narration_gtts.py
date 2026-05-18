"""Generate narration MP3 via gTTS (Google Translate TTS) as Edge-TTS fallback.

Six scenes scripted to align with the Playwright video timeline. Writes
docs/submission/narration.mp3 + docs/submission/narration_timing.json so the
Playwright recorder can sync visual cues to scene boundaries.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from gtts import gTTS

SCENES: list[dict[str, str]] = [
    {
        "id": "intro",
        "text": (
            "Orchestra is a multi-agent framework for third-party risk review, "
            "deployed on Google Cloud Run with Gemini 2.5 Flash. "
            "Today I'll show how it compresses a four-week vendor due-diligence review "
            "into 90 seconds of parallel agent work."
        ),
    },
    {
        "id": "landing",
        "text": (
            "This is the dashboard. Two example packets are pre-loaded. "
            "Acme Cloud Analytics for vendor onboarding, "
            "and HashiCorp Inc. for mergers and acquisitions due-diligence. "
            "I'll run Acme in vendor mode."
        ),
    },
    {
        "id": "pipeline",
        "text": (
            "Click Run Assessment. "
            "The dashboard streams agent execution events live over Server-Sent Events. "
            "Seven specialists run in parallel: Legal, Security, Code, External, Financial, ESG, and SaaS Metrics. "
            "After they join, a Risk Scoring agent produces a zero-to-one-hundred score "
            "with a traffic-light verdict. "
            "A Policy agent applies the rule pack. "
            "A Remediation agent generates a prioritized action plan with contract leverage."
        ),
    },
    {
        "id": "results",
        "text": (
            "Here are the results. "
            "Five specialists contributed findings. "
            "Legal flagged the liability cap below the twelve-month industry norm. "
            "Security flagged a SOC 2 control gap on multi-factor authentication. "
            "External cleared sanctions checks. "
            "Code reviewed the repository license. "
            "And the new ESG specialist flagged a missing net-zero commitment year. "
            "The Risk Scoring agent aggregated these into a structured assessment, "
            "and the Remediation agent produced a P-zero action item "
            "with contract-clause leverage."
        ),
    },
    {
        "id": "why",
        "text": (
            "What makes Orchestra different? "
            "Typed state with merge reducers. "
            "Compile-time graph validation. "
            "A scripted-LLM test harness with three-hundred unit tests. "
            "A cost-aware router. "
            "And a single Cloud-Run-native binary. "
            "The replay JSONL format means demos and CI runs are deterministic — "
            "no Gemini quota burned per pull request. "
            "Compared to LangGraph and CrewAI, Orchestra is the only framework "
            "that's Google AI Studio native by default."
        ),
    },
    {
        "id": "close",
        "text": (
            "Orchestra is open-source on GitHub. "
            "The TPRM application demonstrates the framework's enterprise readiness. "
            "Live demo URL and repository link are on the cover slide. "
            "Thanks for watching."
        ),
    },
]


REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "docs" / "submission"
NARRATION_DIR = OUT_DIR / "narration_scenes"
FFMPEG = REPO_ROOT / "scripts" / "node_modules" / "ffmpeg-static" / "ffmpeg.exe"


def probe_duration(mp3: Path) -> float:
    result = subprocess.run(
        [str(FFMPEG), "-i", str(mp3)],
        capture_output=True, text=True, check=False,
    )
    for line in result.stderr.splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip()
            h, m, s = parts.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


def main() -> None:
    NARRATION_DIR.mkdir(parents=True, exist_ok=True)
    scene_files: list[Path] = []
    timing: list[dict] = []
    for scene in SCENES:
        path = NARRATION_DIR / f"{scene['id']}.mp3"
        print(f"[narrate] {scene['id']}...")
        gTTS(scene["text"], lang="en", tld="com", slow=False).save(str(path))
        duration = probe_duration(path)
        timing.append({"id": scene["id"], "duration_s": round(duration, 2)})
        scene_files.append(path)

    # 0.6s silence between scenes
    silence_path = NARRATION_DIR / "_silence.mp3"
    subprocess.run(
        [str(FFMPEG), "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
         "-t", "0.6", "-q:a", "9", "-acodec", "libmp3lame", str(silence_path), "-y"],
        capture_output=True, check=True,
    )

    concat_list = NARRATION_DIR / "_concat.txt"
    with concat_list.open("w", encoding="utf-8") as f:
        for i, p in enumerate(scene_files):
            f.write(f"file '{p.as_posix()}'\n")
            if i < len(scene_files) - 1:
                f.write(f"file '{silence_path.as_posix()}'\n")

    out_mp3 = OUT_DIR / "narration.mp3"
    subprocess.run(
        [str(FFMPEG), "-f", "concat", "-safe", "0", "-i", str(concat_list),
         "-c:a", "libmp3lame", "-b:a", "128k", str(out_mp3), "-y"],
        capture_output=True, check=True,
    )
    total = probe_duration(out_mp3)
    print(f"[narrate] total duration: {total:.1f}s")

    s = 0.0
    adjusted = []
    for scene in timing:
        adjusted.append({
            "id": scene["id"],
            "start_s": round(s, 2),
            "duration_s": scene["duration_s"],
            "end_s": round(s + scene["duration_s"], 2),
        })
        s += scene["duration_s"] + 0.6
    (OUT_DIR / "narration_timing.json").write_text(
        json.dumps({"total_s": round(total, 2), "scenes": adjusted}, indent=2),
        encoding="utf-8",
    )
    print(f"[narrate] wrote {out_mp3} and narration_timing.json")
    for scene in adjusted:
        print(f"  {scene['id']:10s} {scene['start_s']:6.1f}s → {scene['end_s']:6.1f}s ({scene['duration_s']:5.1f}s)")


if __name__ == "__main__":
    main()
