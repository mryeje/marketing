import json
import subprocess
import argparse
import os

# ---- CONFIG ----
OLLAMA_MODEL = "llama2"  # can swap with "llama2:13b" or other installed model
OUTPUT_RECIPE_FILE = "recipe.json"

# ---- PROMPT TEMPLATE ----
PROMPT_TEMPLATE = """
You are an AI assistant that creates recipe JSON files for converting long videos into short clips.

INPUT = Transcript of a long video.

TASK = Convert transcript into a structured JSON recipe that follows these rules:

- Output JSON must follow this schema:
{
  "src": "<absolute path to source video file>",
  "style_profile": "educational",
  "generate_thumbnails": true,
  "add_text_overlay": true,
  "multi_platform": true,
  "platforms": ["vertical", "square", "landscape"],
  "overlay_text": [...],
  "caption_style": {...},
  "highlight_style": {...},
  "clips": [...]
}

Rules for Clips:
- Each clip is 25–60s long
- Each clip must include: id, label, start, end, duration_sec, overlay_text, subtitles
- Must generate at least 3 clips
- Ensure duration_sec = end - start (seconds)
- Add a thumbnail for each clip
- Include a hook overlay in the first 3 seconds

Now generate the recipe JSON file.
Transcript:
{transcript}
"""

# ---- FUNCTIONS ----
def load_transcript(path):
    """Load transcript from .json or .txt"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            if path.endswith(".json"):
                return f.read()  # pass raw JSON to model
            elif path.endswith(".txt"):
                return f.read()  # plain text transcript
            else:
                print("⚠️ Unsupported file type. Use .json or .txt")
                return None
    except FileNotFoundError:
        print(f"❌ Transcript file not found: {path}")
        return None

def call_ollama(prompt, model=OLLAMA_MODEL):
    """Calls Ollama with subprocess, returns output text."""
    process = subprocess.Popen(
        ["ollama", "run", model],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    output, error = process.communicate(input=prompt)

    if error:
        print("⚠️ Ollama Error:", error)
    return output

def main():
    parser = argparse.ArgumentParser(
        description="Generate recipe JSON for Shorts from a transcript using Ollama LLaMA 2"
    )
    parser.add_argument(
        "transcript_file",
        help="Path to transcript file (.json or .txt)"
    )
    parser.add_argument(
        "-o", "--output",
        default=OUTPUT_RECIPE_FILE,
        help="Output recipe JSON filename (default: recipe.json)"
    )
    args = parser.parse_args()

    transcript = load_transcript(args.transcript_file)
    if not transcript:
        return

    # Fill prompt
    prompt = PROMPT_TEMPLATE.format(transcript=transcript[:5000])  # trim if very long

    print(f"🚀 Sending transcript '{args.transcript_file}' to Ollama...")
    response = call_ollama(prompt)

    # Extract JSON block (try to parse)
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        json_str = response[start:end]

        recipe = json.loads(json_str)

        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(recipe, f, indent=2)

        print(f"✅ Recipe JSON saved to {args.output}")
    except Exception as e:
        print("❌ Failed to parse recipe JSON:", e)
        print("Raw response:\n", response)


if __name__ == "__main__":
    main()
