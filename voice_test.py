import win32com.client

speaker = win32com.client.Dispatch("SAPI.SpVoice")
speaker.Speak("Hello. This is a test of Windows speech.")
