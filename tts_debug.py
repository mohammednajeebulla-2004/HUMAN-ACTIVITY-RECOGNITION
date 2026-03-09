import pyttsx3
import traceback

print("pyttsx3 imported OK")
print("pyttsx3 version:", getattr(pyttsx3, "__version__", "unknown"))

try:
    # On Windows, use SAPI5 engine explicitly
    print("Initializing engine with 'sapi5'...")
    engine = pyttsx3.init("sapi5")
    print("Engine initialized:", engine)

    # List available voices
    voices = engine.getProperty("voices")
    print(f"Found {len(voices)} voices:")
    for i, v in enumerate(voices):
        print(f"  [{i}] id={v.id}")

    # Choose first voice
    if voices:
        engine.setProperty("voice", voices[0].id)

    engine.setProperty("rate", 180)
    engine.setProperty("volume", 1.0)

    print("Speaking test message now...")
    engine.say("This is a test of text to speech from Python.")
    engine.runAndWait()
    print("Finished speaking without exception.")

except Exception as e:
    print("ERROR while using pyttsx3:", e)
    traceback.print_exc()
