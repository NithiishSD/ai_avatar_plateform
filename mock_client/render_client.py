import json
from pathlib import Path


def load_payload():
    """Load the mock render-job payload."""
    payload_path = Path(__file__).parent / "mock_payload.json"

    with open(payload_path, "r", encoding="utf-8") as file:
        return json.load(file)


def viseme_to_mouth(viseme):
    """Convert a viseme into a simple dummy mouth state."""

    mapping = {
        "viseme_sil": "closed",
        "viseme_E": "E_shape",
        "viseme_L": "L_shape",
        "viseme_O": "O_shape",
        "viseme_A": "A_shape",
        "viseme_U": "U_shape",
        "viseme_F": "F_shape",
        "viseme_M": "M_shape"
    }

    return mapping.get(viseme, "closed")


def generate_dummy_render(payload):
    """Generate dummy avatar render states from phoneme timestamps."""

    render_states = []

    for item in payload["phonemeTimestamps"]:
        state = {
            "startMs": item["startMs"],
            "endMs": item["endMs"],
            "phoneme": item["phoneme"],
            "viseme": item["viseme"],
            "mouthState": viseme_to_mouth(item["viseme"]),
            "boundingBox": {
                "x": 100,
                "y": 50,
                "width": 300,
                "height": 400
            }
        }

        render_states.append(state)

    return render_states


def main():
    payload = load_payload()

    print("=" * 50)
    print("MOCK AVATAR RENDER CLIENT")
    print("=" * 50)

    print(f"Job ID: {payload['jobId']}")
    print(f"Avatar ID: {payload['avatarId']}")
    print(f"Duration: {payload['durationMs']} ms")
    print(f"Target FPS: {payload['targetFps']}")
    print(f"Render Quality: {payload['renderQuality']}")

    print("\nPhoneme / Viseme Timeline:")
    print("-" * 50)

    render_states = generate_dummy_render(payload)

    for state in render_states:
        print(
            f"{state['startMs']:4} - "
            f"{state['endMs']:4} ms | "
            f"{state['phoneme']:4} | "
            f"{state['viseme']:12} | "
            f"Mouth: {state['mouthState']}"
        )

    print("\nDummy Avatar Bounding Box:")
    print(render_states[0]["boundingBox"])

    print("\nMock render generated successfully!")


if __name__ == "__main__":
    main()